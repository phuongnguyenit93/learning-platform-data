# Spring AOT, GraalVM Native Image và Native Build Tools liên hệ thế nào?

## 1. Bức tranh tổng thể

Khi biên dịch ứng dụng Spring Boot thành **GraalVM Native Image**, có ba thành phần phối hợp với nhau nhưng giải quyết ba vấn đề khác nhau:

1. **Spring AOT (Ahead-of-Time)** xử lý trước những phần có thể xác định của ứng dụng Spring tại thời điểm build, sinh mã khởi tạo và cung cấp thông tin cần thiết cho môi trường native.
2. **GraalVM Native Image** phân tích chương trình Java và biên dịch phần mã có thể được sử dụng thành tệp thực thi cho hệ điều hành và kiến trúc CPU đích.
3. **GraalVM Native Build Tools** là plugin Maven/Gradle điều phối các bước build, truyền cấu hình cho trình biên dịch Native Image và hỗ trợ tích hợp với quy trình build/test.

Đây là nền tảng của chủ đề **SPRING_BOOT_NATIVE_IMAGE**: sử dụng Spring AOT và GraalVM để tạo bản native, sau đó đánh giá thời gian khởi động, bộ nhớ, tính tương thích, cách đóng gói container và vận hành. Cần phân biệt rõ ba vai trò để biết nên sửa ở đâu khi một bản build thất bại.

| Thành phần | Chịu trách nhiệm chính | Đầu vào tiêu biểu | Đầu ra tiêu biểu |
| --- | --- | --- | --- |
| Spring AOT | Chuẩn bị ứng dụng Spring cho quá trình xử lý tĩnh | Bean definitions, cấu hình Spring, classpath, các `RuntimeHints` | Mã Java sinh thêm cho bootstrap/đăng ký bean, thông tin truy cập động |
| GraalVM Native Image | Phân tích reachability và biên dịch thành executable | Bytecode ứng dụng, thư viện, mã AOT, reachability metadata | Tệp thực thi native theo OS/CPU |
| Native Build Tools | Kết nối quá trình build với Native Image qua Maven/Gradle | Cấu hình plugin, task/goal, toolchain, tham số biên dịch | Quy trình build và test native có thể lặp lại |

**Điểm phân biệt cốt lõi:** Spring AOT hiểu mô hình khởi tạo của Spring; GraalVM Native Image biên dịch chương trình; Native Build Tools giúp hệ thống build gọi các bước phù hợp. Không thành phần nào thay thế hoàn toàn thành phần còn lại.

## 2. Vì sao Spring Boot cần một bước AOT?

Một ứng dụng Spring Boot chạy trên JVM thường có thể thực hiện nhiều việc lúc khởi động: quét component, kiểm tra điều kiện cấu hình, khám phá bean, tạo proxy hoặc sử dụng reflection. JVM hỗ trợ khả năng nạp và khám phá kiểu ở runtime, nên các cơ chế này thường hoạt động mà không cần liệt kê trước mọi kiểu sẽ truy cập.

Ngược lại, GraalVM Native Image dựa trên giả định **closed world**: tại thời điểm build, trình biên dịch cần có đủ thông tin để xác định mã và dữ liệu nào có thể được dùng. Một lời gọi trực tiếp như `new InvoiceService()` tương đối dễ phân tích; việc ghép tên lớp từ chuỗi cấu hình rồi gọi `Class.forName(...)` có thể khiến trình phân tích không nhận ra lớp, constructor hoặc phương thức cần giữ lại.

Spring AOT thu hẹp khoảng cách đó bằng cách:

- Xử lý trước ngữ cảnh Spring trong giai đoạn build và **sinh mã Java** cho các thao tác như đăng ký và khởi tạo bean.
- Cung cấp hoặc tổng hợp **runtime hints** về reflection, JDK dynamic proxy, resource, serialization và một số kiểu truy cập động khác.
- Đưa những quyết định cấu hình có thể xác định sớm sang thời điểm build, giảm phần công việc mà ứng dụng phải làm lúc khởi động.

Ví dụ, với một bean được khai báo bằng `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
class BillingConfiguration {
    @Bean
    BillingService billingService(PaymentGateway gateway) {
        return new BillingService(gateway);
    }
}
~~~

Khi build theo chế độ AOT, Spring có thể sinh các đoạn mã phục vụ đăng ký và tạo bean dựa trên định nghĩa trên. Đoạn mã do công cụ sinh ra là **mã Java dùng trong quá trình build tiếp theo**; nó không phải executable native và không thay cho trình biên dịch của GraalVM.

Một hệ quả quan trọng: các lựa chọn làm thay đổi cấu trúc bean, chẳng hạn một số `@Conditional`, profile hoặc cấu hình dùng khi AOT xử lý ứng dụng, có thể bị cố định trong sản phẩm build. Không nên mặc định rằng đổi biến môi trường ở runtime sẽ tái tạo toàn bộ `ApplicationContext` theo một cấu hình mới như khi chạy JAR trên JVM.

## 3. GraalVM Native Image làm gì sau Spring AOT?

Native Image nhận bytecode đã biên dịch, thư viện liên quan, mã do AOT sinh ra và metadata về khả năng truy cập động. Trình biên dịch thực hiện phân tích **reachability** từ các điểm vào chương trình, xác định những lớp, phương thức và dữ liệu cần giữ lại, rồi tạo mã máy cho nền tảng đích.

Ở thời điểm build, Native Image cần biết về những hoạt động không dễ suy ra bằng phân tích tĩnh, chẳng hạn:

- Khởi tạo một lớp bằng reflection khi tên lớp đến từ chuỗi.
- Gọi constructor hoặc phương thức bằng reflection.
- Đọc tài nguyên trên classpath thông qua tên hoặc pattern được tạo động.
- Tạo JDK dynamic proxy cho danh sách interface cụ thể.
- Serialization/deserialization cần truy cập thành viên mà trình phân tích không tự nhìn thấy.

Thông tin này được cung cấp thông qua **reachability metadata**, trong đó có runtime hints do Spring và thư viện đóng góp. Native Image dùng metadata để quyết định cần giữ khả năng truy cập nào trong executable. Metadata giúp trình biên dịch nhận diện nhu cầu truy cập động, nhưng **không biến native image thành môi trường có thể nạp tùy ý mọi lớp chưa xuất hiện lúc build**.

Sản phẩm có thể chạy mà **không cần cài JVM tại máy chạy**, nhưng vẫn có thể phụ thuộc thư viện hệ điều hành hoặc cơ chế liên kết của nền tảng. Một executable được build cho Linux/x86-64 không thể mặc nhiên chạy trên Windows/ARM64; cần build đúng đích hoặc dùng môi trường build tương thích.

Native Image cũng có những đánh đổi: build thường tốn thời gian và tài nguyên hơn, một số thư viện động cần cấu hình bổ sung, và hiệu năng tải dài hạn có thể khác JVM có JIT. Thời gian khởi động nhanh hay RSS thấp hơn cần được **đo trên cùng ứng dụng và cùng kịch bản**, không coi là bảo đảm cho mọi workload.

## 4. Native Build Tools đứng ở đâu trong chuỗi build?

Native Build Tools cung cấp các plugin chính:

- Maven: `org.graalvm.buildtools:native-maven-plugin`.
- Gradle: `org.graalvm.buildtools.native`.

Plugin quản lý cách gọi `native-image`, nhận cấu hình build arguments, xác định executable và tích hợp các nhiệm vụ build/test native. Khi kết hợp với **Spring Boot Maven/Gradle plugin**, quy trình sẽ gọi bước Spring AOT tại thời điểm thích hợp rồi dùng các đầu ra đó cho Native Image. Nói cách khác, Native Build Tools **không tự phân tích bean theo ngữ nghĩa của Spring** và **không tự thay thế trình biên dịch GraalVM**.

~~~mermaid
flowchart TD
    A["Mã nguồn Spring Boot và dependency"] --> B["Spring AOT: xử lý ApplicationContext"]
    B --> C["Mã khởi tạo sinh ra và runtime hints"]
    C --> D["Biên dịch Java thành bytecode"]
    D --> E["GraalVM Native Image: reachability và native compilation"]
    E --> F["Executable native theo OS/CPU đích"]
    G["Maven / Gradle + Native Build Tools"] -. "điều phối build" .-> B
    G -. "gọi native-image" .-> E
~~~

Sơ đồ mô tả trách nhiệm logic; các bước chi tiết, vị trí thư mục tạm và thứ tự task cụ thể có thể khác giữa Maven, Gradle và phiên bản plugin. Dù dùng công cụ nào, điều quan trọng là **mã và metadata AOT phải được đưa vào quá trình native compilation**.

### Maven: ví dụ quy trình

Trong dự án Spring Boot dùng `spring-boot-starter-parent`, có thể khai báo plugin Native Build Tools cùng Spring Boot Maven plugin:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Với bộ phiên bản Spring Boot và plugin tương thích, parent đã chuẩn bị profile `native`:

~~~bash
./mvnw test
./mvnw -Pnative native:compile
~~~

Lệnh đầu chạy bộ test JVM thông thường. Lệnh sau kích hoạt quá trình tạo native executable với các bước AOT cần thiết. Executable Maven thường nằm trong `target/`, nhưng tên tệp phụ thuộc cấu hình dự án. Trên Windows có thể dùng `mvnw.cmd` thay cho `./mvnw`.

Nếu dự án **không dùng** `spring-boot-starter-parent`, cần thiết lập tương đương cho AOT, compiler và lifecycle/plugin execution; không nên cho rằng profile `native` tự tồn tại. Cũng cần đảm bảo máy build có JDK/GraalVM, công cụ `native-image`, native compiler và các thư viện hệ thống mà toolchain yêu cầu.

### Gradle: ví dụ quy trình

Với Gradle Groovy DSL, ngoài plugin Spring Boot và Java của dự án, bổ sung Native Build Tools:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'org.graalvm.buildtools.native' version '<native-build-tools-version>'
}
~~~

Hai giá trị trong dấu `<...>` là chỗ điền phiên bản thực tế **tương thích với dự án**; giữ nguyên các placeholder sẽ không build được. Sau khi cấu hình dependency và toolchain:

~~~bash
./gradlew test
./gradlew nativeCompile
~~~

Khi plugin Spring Boot và Native Build Tools được tích hợp, task `nativeCompile` sử dụng kết quả AOT. Có thể kiểm tra các task như `processAot`, `nativeCompile` và `nativeTest` trong phiên bản plugin đang dùng. Executable Gradle thường được đặt dưới `build/native/nativeCompile/`. Trên Windows có thể dùng `gradlew.bat`.

**Không có một lệnh Native Build Tools duy nhất áp dụng cho mọi dự án**: cách khai báo version, profile, task và native-test phụ thuộc hệ build. Điều bất biến là nhiệm vụ build phải kết nối được mã AOT với `native-image`.

## 5. Ví dụ: khi nào cần bổ sung RuntimeHints?

Giả sử một ứng dụng đọc tên exporter từ cấu hình và tạo đối tượng qua reflection:

~~~java
String className = "com.example.demo.CsvExporter";
Class<?> type = Class.forName(className);
Object exporter = type.getDeclaredConstructor().newInstance();
~~~

Trên JVM, đoạn mã có thể hoạt động nếu lớp tồn tại trên classpath và truy cập hợp lệ. Khi build native, trình phân tích tĩnh **không nhất thiết xác định được** lớp nào sẽ được tạo từ chuỗi. Nếu không có metadata thích hợp, việc truy cập constructor có thể thất bại lúc chạy native.

Một cách khai báo rõ chủ đích là dùng Spring `RuntimeHintsRegistrar`:

~~~java
package com.example.demo;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ImportRuntimeHints;

@SpringBootApplication
@ImportRuntimeHints(DemoHints.class)
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

class DemoHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CsvExporter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
        hints.resources().registerPattern("reports/*.txt");
    }
}

class CsvExporter {
    public CsvExporter() {}
}
~~~

Trong ví dụ này:

- `@ImportRuntimeHints` yêu cầu Spring nạp registrar; `CsvExporter` được đăng ký cho việc gọi constructor qua reflection.
- Pattern `reports/*.txt` minh họa một resource nằm trên classpath, ví dụ `src/main/resources/reports/sample.txt`, cần được đóng gói để đọc tại runtime.
- Nếu thư viện Spring hoặc framework đã sinh đủ hints cho một kiểu truy cập, **không cần đăng ký trùng**. Hints bổ sung phù hợp cho những hành vi động mà hệ thống chưa biết.

Cần đăng ký **đúng loại truy cập**: giữ constructor không đồng nghĩa với cho phép gọi mọi private method hay dùng mọi hình thức serialization. Với dynamic proxy, resource hoặc serialization, hãy dùng phần tương ứng trong `RuntimeHints` hoặc metadata do thư viện cung cấp. Đừng đăng ký hàng loạt toàn bộ classpath để “chữa” lỗi; điều đó tăng kích thước và làm mất khả năng kiểm soát.

## 6. Phân biệt các thời điểm và trách nhiệm

| Tình huống | Cần xem thành phần nào trước? | Vì sao |
| --- | --- | --- |
| Bean có điều kiện hoạt động khác khi native build | Spring AOT và cấu hình dùng tại build | Điều kiện ảnh hưởng bean graph có thể đã được quyết định khi AOT xử lý |
| Native chạy được nhưng lỗi tạo lớp bằng reflection | Runtime hints/reachability metadata, sau đó Native Image | Kiểu hoặc thành viên dùng động có thể chưa được khai báo |
| Không tìm thấy template/resource trong binary | Resource hints và cách đưa resource vào artifact | Resource có thể không được đưa vào image |
| Build báo không tìm thấy `native-image` hoặc native compiler | Toolchain, Maven/Gradle Native Build Tools | Chưa có hoặc chưa cấu hình đúng trình biên dịch/công cụ hệ thống |
| Native image build hết bộ nhớ hoặc quá chậm | Native Image và cấu hình môi trường build | Native compilation có chi phí CPU/RAM riêng |
| Ứng dụng chạy native sai kiến trúc hoặc thiếu thư viện OS | Nền tảng build, linker và container runtime | Executable phụ thuộc OS/CPU và cách liên kết thư viện |
| JAR chạy được nhưng test chức năng native thất bại | Điểm dùng dynamic feature và bộ test native | Hành vi được JVM hỗ trợ có thể cần thêm metadata hoặc thay đổi cách cài đặt |

Ba khái niệm dễ nhầm:

1. **Spring AOT không đồng nghĩa với GraalVM Native Image.** AOT sinh mã chuẩn bị ứng dụng; Native Image mới biên dịch thành mã máy.
2. **Native Build Tools không đồng nghĩa với `spring-boot-maven-plugin` hoặc `org.springframework.boot` trong Gradle.** Spring Boot plugin cung cấp các tác vụ ứng dụng/AOT; Native Build Tools tích hợp trình biên dịch native. Chúng phối hợp với nhau.
3. **AOT không xóa mọi nhu cầu reflection.** Những phần sử dụng reflection vẫn có thể hoạt động, miễn trình biên dịch có đủ metadata và API được hỗ trợ.

## 7. Trình tự thực hành để xác nhận cả ba đã phối hợp đúng

Giả sử ứng dụng có một HTTP endpoint và một luồng xuất báo cáo sử dụng resource hoặc reflection:

1. **Kiểm tra bản JVM:** chạy unit/integration test, đóng gói JAR và thử endpoint. Bước này thiết lập hành vi chuẩn để so sánh.
2. **Chuẩn bị native toolchain:** dùng phiên bản Java, Spring Boot, GraalVM và Native Build Tools tương thích; kiểm tra lệnh `native-image --version` cùng compiler/linker cần thiết.
3. **Build native bằng Maven hoặc Gradle:** chạy `native:compile` trong profile thích hợp hoặc `nativeCompile`. Kiểm tra log xem bước AOT và Native Image đều được thực thi.
4. **Chạy executable native và kiểm thử các nhánh động:** gọi HTTP endpoint, tạo exporter, tải resource, serialization, kết nối cơ sở dữ liệu và các integration quan trọng. Một ứng dụng khởi động thành công chưa chứng minh mọi nhánh tương thích.
5. **Sửa theo triệu chứng:** điều chỉnh bean/config nếu AOT cố định điều kiện ngoài ý muốn; bổ sung hints cho truy cập động thực sự cần; sửa toolchain khi build compiler thất bại. Build và chạy lại native sau mỗi thay đổi có liên quan.
6. **So sánh hiệu năng công bằng:** đo cùng endpoint, dữ liệu, tài nguyên CPU/RAM, cấu hình và giới hạn container. Tách chỉ số thời gian khởi động, RSS/bộ nhớ thực tế, thông lượng và độ trễ đã warm-up; ghi nhận cả thời gian build và kích thước artifact.

Có thể đóng gói native executable trực tiếp vào container runtime phù hợp hoặc dùng Cloud Native Buildpacks. Ví dụ, với cấu hình Maven/Spring Boot phù hợp và Docker/Buildpacks sẵn sàng:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Buildpacks là **con đường đóng gói và build trong môi trường container**; nó không thay thế bản chất của Spring AOT hoặc Native Image. Ở cách build này, bộ công cụ native có thể được cung cấp trong builder image thay vì phải cài đầy đủ trên máy local. Cần kiểm tra kiến trúc của builder và runtime image khi triển khai.

## 8. Tự kiểm tra cách hiểu

Hãy dùng ba câu sau để xác định nơi chịu trách nhiệm:

- **Ai hiểu `@Bean`, `@Conditional` và có thể sinh mã đăng ký bean?** Spring AOT.
- **Ai phân tích mã có thể được gọi và tạo executable không cần JVM lúc chạy?** GraalVM Native Image.
- **Ai cung cấp goal/task như `native:compile` hoặc `nativeCompile` trong quy trình Maven/Gradle?** Native Build Tools, phối hợp với plugin Spring Boot.

Khi gặp lỗi, lần theo thứ tự **cấu hình Spring ở build time → mã/hints AOT → phân tích và biên dịch Native Image → hành vi thực tế của executable**. Cách phân chia trách nhiệm này giúp phát hiện đúng nguyên nhân, tránh sửa ngẫu nhiên cả Spring config, native arguments và container cùng lúc.
