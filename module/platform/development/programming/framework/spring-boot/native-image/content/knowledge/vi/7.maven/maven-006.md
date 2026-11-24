# Profile `nativeTest` và `spring-boot:process-test-aot`

Khi biên dịch **Spring Boot** thành **GraalVM Native Image**, kiểm thử trên JVM thôi chưa đủ. Mã ứng dụng có thể chạy tốt trên JVM nhưng thất bại trong executable native vì reflection, resource, proxy hoặc cách khởi tạo context khác với lúc chạy JVM. Để kiểm tra những vấn đề này sớm, Maven có thể chạy bộ kiểm thử trong một **native test image**, với sự hỗ trợ của **Spring AOT** và **GraalVM Native Build Tools**.

Trong chương **Maven** của module **`SPRING_BOOT_NATIVE_IMAGE`**, chúng ta sẽ tìm hiểu profile `nativeTest`, goal `spring-boot:process-test-aot` và cách chúng phối hợp trong Maven lifecycle. Bài học gắn trực tiếp với mục tiêu của module: build Spring Boot native bằng Spring AOT, kiểm tra tính tương thích, nhận biết vấn đề reflection/resource, và chuẩn bị cho việc đo startup, bộ nhớ cũng như vận hành executable/container native.

> **Lưu ý phạm vi:** `nativeTest` là **tên profile do dự án khai báo**, thường gặp trong các dự án Spring Boot hỗ trợ native; nó không phải một profile mặc định có mặt trong mọi dự án Maven. Ví dụ dưới đây giả định phiên bản Spring Boot, GraalVM Native Build Tools và JDK/GraalVM được chọn tương thích. Tên và binding của các goal có thể được điều chỉnh theo cấu hình dự án và phiên bản plugin.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **native test** khác gì với test thông thường chạy bằng Maven Surefire trên JVM.
- Phân biệt vai trò của **`spring-boot:process-test-aot`**, **`native:test`** và profile **`nativeTest`**.
- Cấu hình Maven để xử lý test context bằng Spring AOT trước khi tạo và chạy native test image.
- Chạy và đọc kết quả `./mvnw -PnativeTest test`; nhận diện lỗi xảy ra ở bước Java compile, Spring AOT, Native Image hay runtime test.
- Chọn đúng loại kiểm thử khi đánh giá khả năng tương thích trước khi đóng gói Spring Boot Native Image.

## 2. Vì sao cần kiểm thử riêng trên Native Image?

Trên JVM, nhiều thư viện có thể tải lớp động, truy xuất class/member qua reflection và đọc resource từ classpath lúc chương trình hoạt động. GraalVM Native Image sử dụng phân tích khả năng truy cập (**reachability analysis**) khi build; mã và metadata không được nhận biết đúng có thể thiếu khỏi executable cuối cùng.

Ví dụ:

~~~java
Class<?> type = Class.forName("com.example.payment.PaymentAdapter");
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Nếu Native Image không thể suy ra việc truy cập động này và dự án không có **reachability metadata/Runtime Hints** tương ứng, chương trình native có thể thất bại mặc dù unit test trên JVM chạy thành công. Tương tự, một file cấu hình, template hoặc dữ liệu trong `src/main/resources` có thể cần khai báo để Native Image đưa vào binary.

Với Spring Boot, **Spring AOT** phân tích cấu hình Spring và tạo mã/metadata hỗ trợ xây dựng native image. Còn **test AOT** xử lý thêm những cấu hình chỉ xuất hiện ở test: các Spring test context, cấu hình test, thay thế bean, profile test và những nhu cầu liên quan.

Sự khác nhau quan trọng:

| Cách chạy | Môi trường | Phát hiện tốt vấn đề gì? | Giới hạn |
|---|---|---|---|
| `./mvnw test` | JVM và Maven Surefire theo cấu hình mặc định | Logic Java, phần lớn unit/integration test thường | Không chứng minh mã tương thích với phân tích AOT/Native Image |
| `./mvnw -PnativeTest test` | Native test image, khi profile cấu hình đầy đủ | Test context, reflection/resource, hành vi khi test trong native | Tốn thời gian build hơn; không thay thế kiểm thử binary ứng dụng cuối |
| Chạy bản native ứng dụng và gọi endpoint | Executable native của ứng dụng | Startup, wiring thực tế, cấu hình deployment, behavior và tài nguyên runtime | Không tự động chạy toàn bộ assertion JUnit nếu chưa có test harness |

**Một native test image khác với executable ứng dụng.** Nó thường chứa những lớp kiểm thử và thành phần cần thiết để JUnit Platform (hoặc framework test được hỗ trợ) chạy test. Vì vậy, native tests có thể phát hiện lỗi tương thích, nhưng không có nghĩa executable production đã được build, đóng container và kiểm thử đầy đủ.

## 3. Ba thành phần của quy trình

### 3.1. Profile `nativeTest`

**Maven profile** là một tập cấu hình có điều kiện trong `pom.xml` hoặc nơi Maven hỗ trợ. Profile có thể thêm plugin, execution, dependency hoặc property. Chỉ khi profile được kích hoạt, những thay đổi đó mới tham gia vào effective POM của lần build.

Lệnh:

~~~bash
./mvnw -PnativeTest test
~~~

có nghĩa là **kích hoạt profile có id `nativeTest`** rồi thực hiện Maven lifecycle tới phase `test`. Maven không tự hiểu rằng tên `nativeTest` phải chạy Native Image; hành vi đó xuất hiện khi profile đã khai báo plugin/execution thích hợp.

### 3.2. Goal `spring-boot:process-test-aot`

Goal này thuộc **Spring Boot Maven Plugin** (`org.springframework.boot:spring-boot-maven-plugin`). Nhiệm vụ của nó là xử lý **Spring test contexts** bằng cơ chế AOT: phân tích những ngữ cảnh Spring mà test cần, tạo mã hỗ trợ khởi tạo context và chuẩn bị các thông tin cần thiết cho pipeline AOT/native.

Nó **không tự biên dịch executable native** và **không tự chạy JUnit tests**. Nó chuẩn bị phần phía Spring để Native Image có khả năng xây dựng và chạy test đúng cách.

### 3.3. Goal `native:test`

Goal `test` của **GraalVM Native Build Tools Maven Plugin** (`org.graalvm.buildtools:native-maven-plugin`), thường gọi đầy đủ là `native:test`, thực hiện phần việc phía Native Image: sử dụng các test đã biên dịch và cấu hình cần thiết để tạo **native test executable**, sau đó chạy test bằng executable này.

Đừng nhầm hai goal có cùng chữ “test”:

- `spring-boot:process-test-aot`: xử lý **mã và Spring context dành cho test**.
- `native:test`: **biên dịch/chạy test bằng Native Image**.
- Maven lifecycle phase `test`: mốc trong vòng đời Maven, nơi các goal kiểm thử được gắn vào theo cấu hình.

## 4. Cách các bước kết nối trong Maven lifecycle

Với profile native test được cấu hình đúng, dòng xử lý khái niệm là:

~~~mermaid
flowchart TB
    A["mvn -PnativeTest test"] --> B["Kích hoạt profile nativeTest"]
    B --> C["Biên dịch main/test classes theo Maven lifecycle"]
    C --> D["spring-boot:process-test-aot"]
    D --> E["Generated test AOT code và metadata"]
    E --> F["GraalVM native-maven-plugin: test"]
    F --> G["Native Image phân tích và biên dịch test executable"]
    G --> H["Chạy test trong môi trường native"]
    H --> I["Kết quả pass/fail và báo cáo"]
~~~

Các phase Maven liên quan:

| Phase / goal | Vai trò |
|---|---|
| `compile` và các phase chuẩn bị | Biên dịch phần mã ứng dụng và thực hiện các tác vụ cấu hình của dự án |
| `test-compile` | Biên dịch lớp test và nguồn test |
| `process-test-classes` | Một vị trí phù hợp để chạy `process-test-aot` sau khi test classes đã tồn tại |
| `test` | Chạy kiểm thử; profile có thể gắn `native:test` vào đây |

**Thứ tự rất quan trọng:** Spring AOT cần thấy các lớp test/context đã được chuẩn bị. Vì vậy không nên tùy ý đặt `process-test-aot` ở phase quá sớm, hoặc gọi độc lập goal này từ một thư mục `target` chưa có test classes rồi kỳ vọng kết quả giống lifecycle đầy đủ.

Trong các bản plugin có default phase cho `process-test-aot`, Maven có thể tự gắn goal vào phase phù hợp khi execution không khai báo `<phase>`. Ví dụ ở phần sau khai báo `process-test-classes` tường minh để người học nhìn rõ thứ tự. Khi dùng POM được Spring Initializr hoặc bộ công cụ của dự án tạo sẵn, nên giữ cơ chế binding đang hoạt động và kiểm tra effective POM trước khi thêm execution.

## 5. Cấu hình mẫu profile `nativeTest` trong `pom.xml`

Ví dụ tập trung vào một dự án **Spring Boot Maven** đã quản lý phiên bản cho Spring Boot Maven Plugin và GraalVM Native Build Tools. Nếu dự án chưa quản lý phiên bản plugin, phải khai báo phiên bản tương thích qua `<version>` hoặc `<pluginManagement>` tương ứng.

~~~xml
<profiles>
    <profile>
        <id>nativeTest</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.springframework.boot</groupId>
                    <artifactId>spring-boot-maven-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>process-test-aot</id>
                            <phase>process-test-classes</phase>
                            <goals>
                                <goal>process-test-aot</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>

                <plugin>
                    <groupId>org.graalvm.buildtools</groupId>
                    <artifactId>native-maven-plugin</artifactId>
                    <extensions>true</extensions>
                    <executions>
                        <execution>
                            <id>test-native</id>
                            <phase>test</phase>
                            <goals>
                                <goal>test</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Ý nghĩa từng phần:

1. **`<id>nativeTest</id>`**: cho phép bật bằng `-PnativeTest`. Tên này là quy ước dự án; Maven không cung cấp sẵn nội dung profile.
2. **`spring-boot-maven-plugin`**: gọi goal `process-test-aot` khi lifecycle đến `process-test-classes`, tức sau khi mã test được biên dịch.
3. **`native-maven-plugin`**: cung cấp goal `test` để tạo/chạy native test image khi Maven đi đến phase `test`.
4. **`<extensions>true</extensions>`**: sử dụng plugin như Maven extension theo cấu hình này. Cơ chế xử lý lifecycle/test của plugin có thể chịu ảnh hưởng bởi bản phát hành; nên đối chiếu effective POM và log thực thi.

**Đây là mẫu minh họa cấu trúc cần thiết, không phải yêu cầu sao chép vào mọi dự án.** Nếu `pom.xml` đã có profile `nativeTest` và các plugin trên, thêm trùng execution có thể khiến AOT hoặc native test chạy lặp. Hãy kiểm tra cấu hình hiện có trước.

### Có thể viết dưới cấu hình plugin đang tồn tại không?

Có. Trong Maven, plugin có thể được khai báo ở khối `<build><plugins>` chung, còn profile thêm execution hoặc cấu hình điều kiện. Maven sẽ hợp nhất cấu hình plugin theo quy tắc effective POM. Điều cần kiểm tra là **cấu hình cuối cùng khi bật profile**, không chỉ vị trí đoạn XML bạn vừa thêm.

Nếu dự án đa module, không nên đặt execution native test vào mọi module một cách máy móc. Chỉ module có test cần xử lý và có cấu hình Spring Boot/Native Build Tools thích hợp mới nên thực hiện pipeline tương ứng.

## 6. Ví dụ test Spring Boot được xử lý bởi test AOT

Giả sử ứng dụng có một service:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Viết một bài test dùng Spring context:

~~~java
package com.example.demo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class GreetingServiceNativeTests {

    @Autowired
    GreetingService greetingService;

    @Test
    void shouldInjectAndCallService() {
        assertThat(greetingService.greet("Native"))
                .isEqualTo("Hello, Native");
    }
}
~~~

Test giả định dự án có dependency `spring-boot-starter-test` ở scope `test` và có class ứng dụng Spring Boot (`@SpringBootApplication`) ở package thích hợp để `@SpringBootTest` tìm được cấu hình.

Với `./mvnw test`, test thường chạy trên JVM theo cấu hình Maven. Với `./mvnw -PnativeTest test` và profile đã thiết lập, Spring test context liên quan có thể được **phân tích ở build time** rồi sử dụng cho native test execution. Phần tạo native test executable do GraalVM Native Build Tools đảm nhiệm.

### Vì sao không chỉ dùng một unit test thuần Java?

Một unit test như:

~~~java
@Test
void returnsMessage() {
    assertThat(new GreetingService().greet("Native"))
            .isEqualTo("Hello, Native");
}
~~~

vẫn hữu ích và có thể chạy trong native test image nếu được hỗ trợ. Tuy nhiên, nó không kiểm tra việc Spring khởi tạo context, dependency injection hoặc xử lý các cấu hình Spring khi AOT. Vì vậy, trong bộ kiểm thử native nên có ít nhất một vài bài test kiểm tra **Spring context thực tế**, bên cạnh các unit test thuần Java.

Ngược lại, không phải mọi test đều cần `@SpringBootTest`; dùng context lớn cho tất cả các test làm tăng thời gian build và số cấu hình AOT phải xử lý. Chọn mức kiểm thử vừa đủ cho mục tiêu.

## 7. Hướng dẫn chạy: JVM trước, native sau

### Bước 1: xác nhận môi trường build

Trong terminal của dự án Maven:

~~~bash
java -version
native-image --version
./mvnw -version
~~~

Ba lệnh này giúp thấy Java trên `PATH`, công cụ Native Image và JDK mà Maven đang dùng. Chúng **không nhất thiết** trỏ đến cùng một JDK nếu máy có nhiều bộ cài hoặc Maven/plugin cấu hình toolchain riêng.

Để biên dịch native trực tiếp trên host, máy cần một **GraalVM JDK có Native Image**, các plugin Maven phù hợp và công cụ native compiler/linker mà hệ điều hành yêu cầu (ví dụ toolchain C/C++ trên Linux/macOS hoặc Visual Studio C++ Build Tools trên Windows).

### Bước 2: kiểm tra JVM tests trước

~~~bash
./mvnw test
~~~

Nếu bộ test trên JVM còn thất bại, hãy khắc phục lỗi chức năng, dependency hoặc cấu hình Spring trước khi điều tra sai khác Native Image. Native test build thường tốn nhiều thời gian và tài nguyên hơn JVM test.

### Bước 3: kích hoạt profile native test

~~~bash
./mvnw -PnativeTest test
~~~

Khi profile cấu hình đúng, đây là luồng cần quan sát:

1. Maven biên dịch mã ứng dụng và test.
2. Spring Boot plugin xử lý AOT cho test.
3. GraalVM Native Build Tools tạo và chạy native test executable.
4. Maven nhận kết quả pass/fail.

Native test image chứa test và các thành phần cần thiết, vì vậy kích thước artifact và thời gian biên dịch có thể lớn hơn bạn dự đoán từ số lượng test. Test chạy trên native executable nhưng **không có nghĩa toàn bộ unit tests sẽ đạt được tốc độ nhanh hơn so với JVM**, vì thời gian AOT compilation là chi phí riêng của build.

### Bước 4: khi lỗi, xem stack trace/log

~~~bash
./mvnw -PnativeTest test -e
~~~

Nếu cần xem cấu hình plugin và lệnh native chi tiết hơn:

~~~bash
./mvnw -PnativeTest test -X
~~~

Log Maven `-X` rất dài; chỉ bật khi cần tìm nguyên nhân, và xem lại trước khi chia sẻ vì có thể chứa đường dẫn, tham số hoặc dữ liệu cấu hình của môi trường.

### Bước 5: xác minh đúng profile đang hoạt động

Nếu project đã có Maven Help Plugin hoặc có thể phân giải plugin này, có thể kiểm tra:

~~~bash
./mvnw help:active-profiles -PnativeTest
./mvnw help:effective-pom -PnativeTest
~~~

Trong effective POM, tìm execution của `spring-boot-maven-plugin` và `native-maven-plugin`. Nếu không xuất hiện, khả năng cao profile chưa được định nghĩa đúng hoặc cấu hình ở module khác. Đây là bước rất hữu ích khi chạy dự án có parent POM hoặc nhiều submodule.

## 8. Gọi trực tiếp `spring-boot:process-test-aot` có đủ không?

Không. Lệnh:

~~~bash
./mvnw spring-boot:process-test-aot
~~~

chỉ yêu cầu Maven gọi **goal xử lý Spring AOT test**. Nó không tương đương với `./mvnw -PnativeTest test`, vì không mặc nhiên chạy Native Image compilation hoặc thực thi native tests.

Hơn nữa, goal này cần đầu vào phù hợp như **test classes và thông tin test context**. Nếu chạy trực tiếp khi dự án chưa trải qua các phase chuẩn bị, goal có thể không tìm thấy dữ liệu cần thiết hoặc cho kết quả không giống pipeline chính thức.

Một cách thử từng phần, tùy phiên bản Spring Boot/plugin:

~~~bash
./mvnw test-compile spring-boot:process-test-aot
~~~

Lệnh trên đi qua phase `test-compile` trước khi gọi goal, nhưng **chưa chạy native:test**. Nó có ích để phân tách lỗi AOT và lỗi Native Image khi điều tra. Để thử đúng đường build đã cấu hình, vẫn ưu tiên:

~~~bash
./mvnw -PnativeTest test
~~~

### `process-aot` khác `process-test-aot` như thế nào?

| Goal | Đầu vào trọng tâm | Kết quả mong muốn |
|---|---|---|
| `spring-boot:process-aot` | Cấu hình ứng dụng, bean definitions và runtime behavior liên quan của phần `main` | Mã/metadata AOT phục vụ ứng dụng |
| `spring-boot:process-test-aot` | Cấu hình và Spring test contexts của phần `test` | Mã/metadata AOT giúp native tests khởi chạy đúng Spring context |
| `native:compile` hoặc goal native build của plugin | Mã đã biên dịch và metadata của ứng dụng | Native executable ứng dụng |
| `native:test` | Test classes, framework test và metadata cần thiết | Native test executable và kết quả kiểm thử |

Đặc biệt, **không thay `process-test-aot` bằng `process-aot` rồi kỳ vọng test contexts tự được xử lý**. Thông tin đặc thù của test (test configuration, test profile, context customizer) khác với cấu hình chính của ứng dụng.

## 9. Vị trí đầu ra và cách đọc kết quả

Trong quy trình Maven/Spring Boot, mã và metadata AOT thường xuất hiện dưới cây thư mục **`target`**, chẳng hạn trong vùng output dành cho Spring AOT. Đường dẫn cụ thể có thể thay đổi theo phiên bản Spring Boot và cấu hình plugin; vì vậy hãy tìm thông tin ở **log của goal `process-test-aot`** thay vì dựa vào một đường dẫn cứng.

Sau khi Maven hoàn thành, nên xác minh:

- **AOT test processing** đã được thực thi thực sự; log phải cho thấy goal Spring Boot tương ứng.
- **Native test image** đã được build bằng GraalVM; nhìn dòng native compiler thay vì chỉ thấy Maven Surefire chạy JVM.
- **Test assertions** được thực thi và kết quả pass/fail rõ ràng.
- Báo cáo kiểm thử trong thư mục output của Maven có thông tin cần thiết; vị trí/định dạng báo cáo chịu ảnh hưởng bởi plugin và cấu hình dự án.

Không nên khẳng định “native tests pass” chỉ vì Maven exit code bằng 0 nếu profile không hề gọi native plugin. Trường hợp đó có thể chỉ là một lần chạy JVM tests hoặc không có test nào được chọn.

## 10. Những điểm có thể không tương thích với test AOT

### 10.1. Spring test context thay đổi hoàn toàn tại runtime

Spring AOT cần **phân tích trước** cấu hình context. Một test tạo hoặc điều chỉnh bean definitions bằng cách chỉ phát hiện ở runtime có thể khó xử lý khi native test image đã được biên dịch. Điều này không có nghĩa mọi cơ chế test của Spring đều bị cấm; cần xem cách chúng tương tác với quá trình AOT theo phiên bản Spring.

Ví dụ, nếu test chọn cấu hình hay implementation bằng chuỗi class name động, hãy kiểm tra xem Native Image có metadata và code phù hợp không.

### 10.2. Mock, spy và proxy động

Những test sử dụng Mockito hoặc kỹ thuật sinh proxy/subclass tại runtime có thể gặp hạn chế trong môi trường native, tùy phiên bản thư viện và cách tạo đối tượng. Cơ chế mock/spy đặc biệt nhạy cảm nếu dựa vào tạo bytecode hoặc nạp class động.

Không nên vội loại bỏ mọi mock. Thay vào đó, phân loại test nào là unit test thuần JVM, test nào cần Spring context thật, và test nào thật sự mang lại giá trị trong native test image. Nếu một test đòi hỏi hành vi động không được hỗ trợ, cân nhắc dùng implementation test đơn giản hoặc kiểm thử ở mức khác.

### 10.3. Reflection hoặc resource bị thiếu

Nếu test dùng:

~~~java
getClass().getResourceAsStream("/fixtures/sample.json");
~~~

hoặc tạo object qua reflection, khả năng chạy tốt trên JVM không bảo đảm resource/class sẽ được nhận biết trong Native Image. Khi có lỗi native, cần phân biệt:

- Resource có nằm đúng nơi cần thiết trong Maven test classpath không?
- Spring AOT/Runtime Hints hoặc reachability metadata đã khai báo các truy cập động cần thiết chưa?
- Tên resource/đường dẫn có khác khi chạy test image không?

Các thao tác như `RuntimeHints.resources().registerPattern(...)` hoặc khai báo reflection phù hợp có thể cần thiết, nhưng phải dựa trên lỗi và mã cụ thể; không thêm metadata tràn lan.

### 10.4. Công nghệ test đòi hỏi tác động đến tiến trình JVM

Test dùng Java agent, instrumentation, attach API hoặc giả định có JVM JIT/classloader đầy đủ có thể không hoạt động trong native executable. Native test image không phải một JVM có đầy đủ các khả năng thay đổi bytecode động.

### 10.5. Thiếu tài nguyên hệ điều hành

Native Image cần compiler/linker thích hợp. Test tích hợp còn có thể cần database, broker, Docker hoặc dịch vụ bên ngoài, tùy cách dự án viết test. Lỗi “không kết nối được database” sau khi image build thành công không tự động là lỗi AOT.

## 11. Chẩn đoán lỗi theo giai đoạn

| Giai đoạn | Dấu hiệu | Cách điều tra |
|---|---|---|
| Maven profile | `-PnativeTest` vẫn không gọi native plugin | Kiểm tra profile tồn tại, effective POM, vị trí module thực thi |
| Java/test compile | Lỗi `Compilation failure` hoặc test code không hợp lệ | Kiểm tra JDK compiler, `maven-compiler-plugin`, dependencies và Java release |
| Spring test AOT | Goal `process-test-aot` lỗi phân tích context/test configuration | Đọc exception từ Spring AOT và cấu hình test; xác định context gây lỗi |
| Native image analysis | Không nhận biết reflection/resource hoặc phát hiện class initialization không an toàn | Xem diagnostic Native Image, bổ sung metadata/đổi initialization phù hợp |
| Native compilation/linking | Không tìm thấy `native-image`, C/C++ compiler/linker, thư viện OS | Kiểm tra GraalVM JDK, PATH/toolchain và yêu cầu hệ điều hành |
| Native test runtime | Assertion fail, không dựng được context, thiếu resource ở runtime | Phân biệt lỗi logic và lỗi native behavior; dùng stack trace, test logs |
| Báo cáo | Build thành công nhưng không có test native | Xác nhận test goal đã chạy, bộ test được chọn và số lượng test thực thi |

### Tình huống A: `process-test-aot` thành công nhưng `native:test` thất bại

Điều này hoàn toàn có thể xảy ra. Spring AOT chỉ xử lý phần phía Spring, còn Native Image phải phân tích/biên dịch toàn bộ đồ thị code và test framework. Kiểm tra **thông báo lỗi đầu tiên của Native Image**: thiếu metadata, object bị giữ từ build time, unsupported feature hay lỗi native linker?

**Không thêm bừa một goal Spring Boot nữa** nếu lỗi xảy ra ở bước Native Image.

### Tình huống B: `native:test` build xong nhưng một test `@SpringBootTest` lỗi

Kiểm tra context và test-specific configuration. Nếu test chỉ thất bại khi native, so sánh cách test dùng reflection, resource, mocks/proxies, profile và các dependency tùy môi trường. Việc khởi tạo context có thể được xử lý bằng mã AOT, vì vậy thay đổi context tùy tiện lúc chạy có thể không mang lại kết quả như trên JVM.

### Tình huống C: gọi `spring-boot:process-test-aot` rồi kết luận native tests đã chạy

Đây là kết luận sai: goal AOT không tự build test executable. Cần kiểm tra `native:test` hoặc pipeline đã gắn goal tương đương vào lifecycle.

### Tình huống D: `./mvnw -PnativeTest test` pass quá nhanh

Native test compilation có thể nhanh hơn khi đã có cache, nhưng nếu không thấy log native compiler hoặc không có test count, hãy xem effective POM, report và profile activation. Có thể profile không chứa execution native, hoặc toàn bộ tests bị skip/chưa được phát hiện.

## 12. Native tests khác kiểm thử native executable production

Native tests có giá trị cao vì chạy JUnit tests dưới Native Image và kiểm thử khả năng tương thích của Spring test context. Dẫu vậy, quy trình triển khai vẫn nên kiểm tra **executable ứng dụng cuối**:

1. Build native application với profile/goal của dự án (chẳng hạn `./mvnw -Pnative native:compile`, nếu POM có profile `native` đúng).
2. Khởi động executable trên hệ điều hành/kiến trúc dự kiến.
3. Kiểm tra endpoint, dữ liệu, database migration, environment variables, secret/configuration, resource và serialization thực tế.
4. Nếu đóng gói container, chạy thử image với cấu hình vận hành tương đương deployment.
5. Đo startup và memory trên bản JVM và bản native với cùng workload/hạ tầng.

**Native test image không phải artifact dùng để deploy.** Kết quả pass của native tests là tín hiệu tốt về tính tương thích, nhưng không thay thế smoke test, integration test của executable production và kiểm thử container.

### Tách hai profile `native` và `nativeTest`

Nhiều dự án dùng quy ước:

| Profile | Mục đích | Lệnh ví dụ |
|---|---|---|
| `native` | Build native executable của ứng dụng | `./mvnw -Pnative native:compile` |
| `nativeTest` | Build/chạy native test image | `./mvnw -PnativeTest test` |

Đây là **quy ước trong POM**, không phải chức năng tự kích hoạt theo tên profile. Một dự án có thể đặt tên khác hoặc gộp cấu hình, miễn goal và lifecycle rõ ràng.

Trong CI, thường nên chạy unit tests JVM trước để phản hồi nhanh, rồi native tests khi cần xác nhận tính tương thích. Sau đó mới build/deploy bản native application và chạy smoke tests. Độ sâu của pipeline còn tùy độ lớn dự án và ngân sách build.

## 13. Lưu ý cho dự án Maven nhiều module

Với multi-module Maven, parent POM có thể quản lý plugin nhưng không phải module nào cũng chứa Spring Boot application hoặc test Spring context. Nếu đặt `nativeTest` trên parent:

- Xác định module chứa test cần chạy native.
- Kiểm tra plugin execution được kế thừa hay chỉ được quản lý qua `pluginManagement`.
- Đừng giả định tất cả module đều có `spring-boot-maven-plugin` và cùng AOT test configuration.
- Khi điều tra lỗi, chạy tại module phù hợp hoặc dùng `-pl` cùng các lựa chọn reactor tương ứng của Maven.

Ví dụ (thay `app-service` bằng artifact/module thật):

~~~bash
./mvnw -pl app-service -am -PnativeTest test
~~~

Lệnh có thể khiến Maven chạy phase `test` cho cả các module phụ thuộc trong reactor. Nếu chỉ module ứng dụng được cấu hình native test, cần xem phản ứng của toàn bộ reactor và mục tiêu kiểm thử thực tế trước khi dùng lệnh này trong CI. Không đưa một profile native test vào toàn bộ module nếu có thể tránh phạm vi build thừa.

## 14. Bài tập thực hành

**Bài tập 1 — Kiểm tra profile:** Một dự án có lệnh `./mvnw -PnativeTest test` chạy thành công. Làm sao xác minh test thực sự chạy trên Native Image?

**Gợi ý đáp án:** xem effective POM và log để xác nhận goal `process-test-aot` và `native:test` đã chạy; tìm bước biên dịch native test image, số test thực thi và báo cáo. Maven exit code 0 một mình chưa đủ.

**Bài tập 2 — Sai mục đích goal:** Nhóm chạy `./mvnw spring-boot:process-test-aot` và cho rằng đã hoàn tất kiểm thử native. Thiếu bước gì?

**Gợi ý đáp án:** thiếu bước biên dịch/thực thi native tests bằng GraalVM Native Build Tools, thường là goal `native:test` trong lifecycle đã được cấu hình.

**Bài tập 3 — Lỗi resource:** Một test mở `/fixtures/sample.json`, pass trên JVM nhưng lỗi khi chạy native. Hãy nêu ba vị trí kiểm tra.

**Gợi ý đáp án:** kiểm tra file và test classpath; kiểm tra reachability/resource metadata/Runtime Hints; kiểm tra đường dẫn truy cập và log runtime test image.

**Bài tập 4 — Bản native thật:** `nativeTest` pass nhưng executable production crash vì đọc biến môi trường khác lúc build. Có mâu thuẫn không?

**Gợi ý đáp án:** không. Native test image và executable ứng dụng khác nhau; chúng có thể dùng cấu hình initialization, môi trường và workload khác. Cần kiểm tra runtime behavior của production executable.

**Bài tập 5 — Chẩn đoán AOT:** Maven báo lỗi từ `spring-boot:process-test-aot` khi khởi tạo một Spring test context. Có nên thay ngay JDK Native Image?

**Gợi ý đáp án:** chưa có bằng chứng cần thay JDK. Trước hết đọc exception về test context/AOT, thử cô lập test và cấu hình Spring. Chỉ kiểm tra phiên bản JDK/GraalVM khi log cho thấy vấn đề tương thích hoặc toolchain.

## 15. Checklist áp dụng vào dự án

- [ ] POM có cấu hình profile `nativeTest`, không chỉ truyền một tên profile chưa được định nghĩa.
- [ ] Spring Boot Maven Plugin có execution `process-test-aot` tại phase phù hợp sau `test-compile`.
- [ ] GraalVM Native Build Tools có goal `test` được gắn vào pipeline để tạo/chạy native test image.
- [ ] Phiên bản Java, Spring Boot, GraalVM Native Image và các Maven plugin tương thích.
- [ ] GraalVM có executable `native-image` và toolchain C/C++/linker của OS đầy đủ.
- [ ] Các test JVM cơ bản pass trước khi chạy build native tốn chi phí.
- [ ] Test `@SpringBootTest` đại diện kiểm chứng Spring test context thực tế.
- [ ] Lỗi reflection/resource và cơ chế mock/proxy được điều tra trong môi trường native.
- [ ] Log và báo cáo xác nhận native test image đã được chạy, số lượng test rõ ràng.
- [ ] Có smoke/integration tests riêng cho executable/container ứng dụng cuối cùng.
- [ ] Startup, memory và tính tương thích được đo/đánh giá ở ứng dụng deploy, không suy ra từ kết quả test image.

**Ghi nhớ:** profile **`nativeTest`** điều phối pipeline qua Maven; goal **`spring-boot:process-test-aot`** chuẩn bị mã và metadata AOT cho Spring test contexts; goal **`native:test`** của GraalVM Native Build Tools tạo và chạy native test image. Ba phần phối hợp giúp phát hiện vấn đề tương thích trước khi phát hành ứng dụng Spring Boot Native Image, nhưng kết quả native tests vẫn cần được bổ sung bằng kiểm thử executable/container thật.
