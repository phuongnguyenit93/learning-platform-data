# Quan hệ giữa `classes`, `test`, `check`, `assemble` và `build` trong Gradle/Spring Boot

## 1. Bức tranh tổng thể: năm task là năm mức trách nhiệm khác nhau

Khi làm việc với **Spring Boot Build Tooling Packaging**, việc hiểu những lệnh Gradle này giúp bạn trả lời chính xác: mã đã biên dịch chưa, test đã chạy chưa, chất lượng đã được kiểm chứng chưa, gói triển khai đã được tạo chưa và lệnh `build` thực sự bảo đảm điều gì?

Đây là **task của Gradle** (đặc biệt khi áp dụng `java` plugin), không phải năm phase liên tiếp của Maven. Gradle xây dựng *đồ thị phụ thuộc task* từ plugin và build script, rồi thực thi các task cần thiết. Vì thế không có quy tắc “phải tự chạy `classes` rồi `test` rồi `check` rồi `assemble` rồi `build`”; gọi một task sẽ kéo theo các task mà nó phụ thuộc.

| Task | Câu hỏi nó trả lời | Kết quả chính | Điều **không** được mặc định suy ra |
| --- | --- | --- | --- |
| `classes` | Main Java source và resource đã sẵn sàng chưa? | Main `.class` và resource đã xử lý trong `build/classes`, `build/resources` (mặc định). | Chưa chứng minh test đạt hoặc JAR đã được tạo. |
| `test` | Bộ test mặc định chạy được và đạt không? | Biên dịch test, thực thi các test mà cấu hình phát hiện, test report. | Không mặc nhiên tạo executable JAR, không tự gọi mọi bộ integration test. |
| `check` | Các kiểm tra được nối vào vòng xác minh đã đạt không? | Tổng hợp `test` và những verification task được plugin/dự án nối thêm. | Không phải công cụ tự động quét mọi loại lỗi; không bắt buộc package. |
| `assemble` | Các artifact phân phối được cấu hình đã đóng gói chưa? | `jar`/`war`, và `bootJar`/`bootWar` khi Spring Boot plugin cấu hình. | Không mặc định chạy `test`, nên artifact có thể được tạo dù test logic đang hỏng. |
| `build` | Đã thực hiện cả nhánh đóng gói lẫn nhánh kiểm chứng chưa? | Phụ thuộc **`assemble` và `check`** cùng các task nối vào chúng. | Không tự chứng minh ứng dụng chạy đúng trong môi trường triển khai. |

**Phân biệt cốt lõi:** `assemble` hướng đến *artifact*, `check` hướng đến *verification*, `build` gom cả hai. `classes` và `test` là các mắt xích cụ thể ở bên dưới.

### “Vòng đời” của Gradle không đồng nghĩa thứ tự tuyến tính

Trong Java plugin, quy tắc khung là:

- `classes` phụ thuộc các task chuẩn bị main output (thường gồm `compileJava` và `processResources`).
- `test` phụ thuộc việc chuẩn bị test classes và classpath; cần main output của dự án theo quan hệ được Gradle thiết lập.
- `check` phụ thuộc `test`; các plugin hoặc cấu hình bổ sung có thể thêm kiểm tra.
- `assemble` phụ thuộc `jar` trong Java plugin; khi Spring Boot plugin cấu hình Java application, `assemble` còn phụ thuộc `bootJar`.
- `build` phụ thuộc **cả `check` và `assemble`**.

Hình sau là **sơ đồ khái niệm rút gọn** cho một ứng dụng Spring Boot áp dụng Java plugin. Mũi tên `A --> B` có nghĩa “A cần B”; sơ đồ lược bỏ nhiều task nội bộ và plugin tùy chọn:

~~~mermaid
flowchart TD
    B["build"] --> C["check"]
    B --> A["assemble"]
    C --> T["test"]
    T --> TC["testClasses"]
    TC --> CT["compileTestJava"]
    TC --> PTR["processTestResources"]
    CT -. "sử dụng main output" .-> CL["classes"]
    A --> J["jar (plain archive)"]
    A --> BJ["bootJar (Spring Boot executable)"]
    J --> CL
    BJ --> CL
    CL --> CJ["compileJava"]
    CL --> PR["processResources"]
~~~

Các task thực tế có thể thêm/bớt theo phiên bản plugin, ngôn ngữ (Kotlin/Groovy), source set, task bị tắt và build script. **Quan hệ phụ thuộc không ép `check` chạy trước `assemble` hoặc ngược lại**: hai nhánh là các điều kiện để `build` hoàn tất. Gradle chọn lịch chạy hợp lệ dựa vào đồ thị; không diễn giải thứ tự log mẫu thành hợp đồng cố định.

## 2. `classes`: chuẩn bị phần mã và tài nguyên production

Với Java plugin và source set `main` mặc định:

- `compileJava` biên dịch `src/main/java` thành `.class`.
- `processResources` xử lý/sao chép `src/main/resources` vào thư mục output tài nguyên.
- `classes` là **lifecycle task gom việc chuẩn bị main output**; thường bản thân không tạo thêm file riêng.
- Những tác vụ bổ sung (annotation processing, tạo code, Kotlin compilation...) có thể được nối vào source set tùy plugin.

Ví dụ:

~~~text
src/main/java/com/example/lifecycle/LifecycleApplication.java
src/main/resources/application.properties
       |
       +--> compileJava ------> build/classes/java/main/...
       |
       +--> processResources -> build/resources/main/...
                              |
                           classes
~~~

Dấu ba chấm biểu thị các file cụ thể do dự án quyết định. Việc Java class có thể biên dịch **không chứng minh** Spring application khởi động được, dependency runtime đầy đủ hoặc test đã chạy. Ngược lại, lệnh `./gradlew classes` hữu ích khi đang sửa lỗi compile và muốn có phản hồi nhanh mà chưa cần package/test.

~~~bash
# macOS/Linux, trong thư mục gốc dự án Gradle
./gradlew classes

# Windows
gradlew.bat classes
~~~

Khi thành công, bạn có thể kiểm tra thư mục output đúng theo source set đang dùng. Nếu `processResources NO-SOURCE`, đó có thể là kết quả hợp lệ khi không có resource; nếu dự án đáng lẽ phải có `application.yml` hay template, cần điều tra đường dẫn hoặc cấu hình source set.

## 3. `test`: chạy test, không đồng nhất với `classes`

Java plugin tạo source set `test` và các task thường gặp:

1. `compileTestJava` biên dịch `src/test/java`, dựa trên test compile classpath và main output.
2. `processTestResources` chuẩn bị `src/test/resources`.
3. `testClasses` gom output cần để chạy test.
4. `test` là task loại `Test`, thực thi những test được cấu hình/engine nhận diện bằng test runtime classpath, rồi viết kết quả.

Thường thấy thứ tự phụ thuộc như sau:

~~~text
main compilation/resources
          |
     test compilation/resources
          |
      testClasses
          |
         test
          |
 test report / test result
~~~

Điều kiện để `test` thực sự đánh giá hành vi là **có test được phát hiện và engine tương ứng được cấu hình**. Ví dụ JUnit Jupiter cần dependency test và `useJUnitPlatform()` trong nhiều dự án Gradle Java. Một task `test` trả thành công nhưng có trạng thái `NO-SOURCE`, bị `SKIPPED` hoặc không phát hiện test chưa đủ làm bằng chứng “đã kiểm thử đầy đủ”.

~~~bash
./gradlew test

# Chỉ chạy một test class khi cần phản hồi nhanh
./gradlew test --tests com.example.lifecycle.LifecycleApplicationTest
~~~

Báo cáo Java plugin thường tại:

~~~text
build/test-results/test/     # dữ liệu kết quả test (thường là XML)
build/reports/tests/test/    # báo cáo HTML, nếu bật output tương ứng
~~~

Đường dẫn có thể đổi khi dự án cấu hình test task/source set khác. `test` mặc định không bảo đảm test tích hợp với DB, message broker, Docker hoặc hệ thống ngoài đã chạy; những bài đó có thể được đặt trong task `integrationTest` riêng và phải được cấu hình vào gate phù hợp.

**Hiểu kết quả test:** Gradle có thể in `UP-TO-DATE` hoặc `FROM-CACHE` nếu kết quả hợp lệ được tái sử dụng; đó khác với “vừa thực thi lại từng test”. Khi điều tra lỗi, có thể chủ động yêu cầu thực thi lại bằng `./gradlew test --rerun-tasks`, nhưng không cần tắt cache trong mọi lần build.

## 4. `check`: điểm tổng hợp các kiểm tra bắt buộc

`check` là một **lifecycle task** do Base plugin cung cấp; Java plugin nối `test` vào `check`. Khi gọi:

~~~bash
./gradlew check
~~~

Gradle sẽ chọn các verification task được khai báo phụ thuộc, thông thường gồm `test`. Nếu dự án áp dụng plugin kiểm tra chất lượng hoặc tự thêm kiểm tra, chúng **chỉ được bảo đảm xuất hiện trong `check` khi thực tế được nối vào đồ thị**.

Ví dụ Groovy DSL dưới đây là đoạn cấu hình **chỉ dùng khi dự án đã đăng ký task `integrationTest`**:

~~~groovy
// build.gradle — đoạn bổ sung sau khi task integrationTest đã tồn tại
tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

Đoạn này **không tự tạo** task `integrationTest`; nếu chưa đăng ký, cấu hình sẽ không hợp lệ. Việc tạo source set, dependency và môi trường chạy integration test phải được làm ở nơi phù hợp trước khi nối gate. Nguyên tắc áp dụng tương tự với checkstyle, SpotBugs, coverage verification, license scan hoặc contract test: đừng suy ra “check sẽ tự chạy tất cả” chỉ vì plugin xuất hiện trong build file.

### `dependsOn`, `mustRunAfter` và `shouldRunAfter` khác nhau

- `dependsOn('integrationTest')`: yêu cầu task mục tiêu **được đưa vào** đồ thị khi chạy `check`.
- `mustRunAfter('test')`: nếu *cả hai task đã được chọn*, yêu cầu thứ tự; **không tự kéo task còn lại vào đồ thị**.
- `shouldRunAfter('test')`: thứ tự ưu tiên mềm khi cả hai task chạy; không tương đương dependency bắt buộc.

Chỉ dùng rule thứ tự không đủ để thiết lập quality gate. Nếu muốn `build` không đạt khi integration test thất bại, hãy nối task đó vào `check` bằng dependency thật, xác nhận nó có test và assert kết quả như dự kiến.

Một task aggregator như `check` có thể không tự viết ra file riêng. **Bằng chứng đúng** là kết quả của các verification task bên dưới, số test, report và lỗi cụ thể; không phải chỉ một dòng `:check`.

## 5. `assemble`: gom các sản phẩm phân phối

Trong Java plugin thuần, `assemble` được gắn với `jar` và những archive task mà plugin khác nối thêm. `jar` thường đóng gói **main classes/resource** thành JAR thư viện/thông thường. JAR này không tự chứa mọi runtime dependency và có thể không chạy độc lập bằng `java -jar`.

Với Spring Boot Gradle plugin:

- Khi áp dụng cả Spring Boot plugin và `java` plugin, thường có task `bootJar` tạo **executable Spring Boot JAR** bao gồm cấu trúc loader và runtime dependency.
- `assemble` tự động phụ thuộc `bootJar`; vì vậy `./gradlew assemble` và `./gradlew build` sẽ kéo task đóng gói Boot JAR (nếu chưa bị tùy chỉnh/tắt).
- Nếu áp dụng `war` plugin cho ứng dụng WAR, Spring Boot plugin cung cấp `bootWar` và nối vào `assemble`.
- Thông thường `jar` vẫn tồn tại và sinh bản archive “plain” với classifier `plain`, trong khi `bootJar` sinh bản executable. Plugin/build script có thể đổi classifier, tên hoặc tắt plain JAR.

~~~bash
# Đóng gói theo những artifact đã nối vào assemble
./gradlew assemble

# Chỉ yêu cầu executable Spring Boot JAR
./gradlew bootJar
~~~

Đầu ra thường nằm ở `build/libs/`. Để phân biệt archive, hãy quan sát **tên file thật và nội dung thật**:

~~~bash
# Thay tên artifact theo kết quả build/libs của chính dự án
jar tf build/libs/lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

Với executable Spring Boot JAR điển hình, bạn sẽ thấy `BOOT-INF/classes/`, `BOOT-INF/lib/` và `META-INF/MANIFEST.MF`. Kiểm tra manifest/loader và thử `java -jar` khi cần xác minh nó thực sự chạy được. Đừng chọn nhầm file `*-plain.jar` để triển khai như executable application.

**Điểm dễ nhầm:** `assemble` không mặc định phụ thuộc `test`. Một build script có thể tùy biến điều này nhưng **không được giả định**. Nếu bạn sửa test khiến một assertion thất bại, `./gradlew assemble` vẫn có thể thành công khi mã production biên dịch/đóng gói bình thường. Vì vậy “đã có JAR” không đồng nghĩa “đã qua kiểm chứng”.

## 6. `build`: phép hợp của `check` và `assemble`, nhưng không phải phép màu

Base/Java plugin thiết lập:

~~~text
build
  +-- check
  |     +-- test
  |     +-- các verification task khác đã được nối
  |
  +-- assemble
        +-- jar
        +-- bootJar (khi Spring Boot + Java plugin được cấu hình)
~~~

Khi gọi `./gradlew build`, Gradle giải quyết và thực thi tất cả dependency cần thiết của cả hai nhánh. Build đạt khi không có task bắt buộc nào thất bại theo chính sách thực thi đã chọn. Bài học quan trọng:

1. `build` **không tương đương** chuỗi lệnh thủ công `classes test check assemble build`; nhiều task trùng sẽ được lên kế hoạch và quản lý theo đồ thị.
2. `build` không tự thêm integration test, security scan, smoke test hoặc deploy. Muốn có chúng như gate, cần khai báo dependency hoặc pipeline rõ ràng.
3. `build` không buộc `assemble` chạy sau toàn bộ `check`. Nếu test lỗi, vẫn có thể thấy file archive do nhánh package đã chạy trước; **kết luận build phải dựa vào trạng thái toàn bộ invocation**, không dựa vào sự tồn tại file.
4. Build thường **incremental**: Gradle đánh dấu một task `UP-TO-DATE` hoặc dùng build cache khi input/output phù hợp. `clean` là task khác, **không tự nằm trong `build`**.
5. Chạy `build -x test` hoặc tắt `test.enabled` có thể khiến lệnh xanh mà không thực thi test; chất lượng “đạt” phải dựa trên gate đúng, không chỉ `BUILD SUCCESSFUL`.

~~~bash
# Kiểm chứng chuẩn, chạy incrementally
./gradlew build

# Dọn output cũ rồi chạy chuỗi build trong cùng invocation
./gradlew clean build

# Hiển thị task dự kiến, không thực thi chúng
./gradlew build --dry-run
~~~

**`--dry-run` là công cụ đọc đồ thị, không phải bài test.** Trong output dry-run có thể thấy task kèm chữ `SKIPPED` vì đang mô phỏng; đừng hiểu đó là kết quả test thực tế. `clean build` có ích khi cần loại bỏ output cũ để chẩn đoán, nhưng không chứng minh build hoàn toàn độc lập mạng/cache hay là “reproducible build” ở mức byte nếu dependency không được kiểm soát.

### Bảng chọn lệnh theo mục tiêu

| Bạn muốn... | Ưu tiên gọi | Vì sao |
| --- | --- | --- |
| Kiểm tra lỗi biên dịch mã main thật nhanh | `classes` | Đỡ chạy test/đóng gói không cần thiết. |
| Xác minh unit test đang sửa | `test`, tùy trường hợp `--tests` | Có test report; không cần archive. |
| Chạy toàn bộ verification đã đăng ký | `check` | Có các gate nối vào check. |
| Tạo executable Spring Boot JAR để thử runtime | `bootJar`, hoặc `assemble` | Tập trung vào package; nhớ test riêng nếu cần. |
| Tạo artifact **và** chạy verification ở cấp dự án | `build` | Kéo hai nhánh `assemble` + `check`. |
| Kiểm tra build có gọi đúng task không | `build --dry-run` và `tasks --all` | Phát hiện task thật/khác biệt plugin và cấu hình. |

## 7. Thực hành có thể chạy: theo dõi năm task trên một ứng dụng nhỏ

Ví dụ sau dùng **Gradle Groovy DSL, Java 17+, Spring Boot 3.3.13**. Đây là một dự án độc lập; nếu bạn đã có project, dùng phiên bản plugin/JDK đã được quy định trong project đó. Mục tiêu của bài là quan sát task graph, không yêu cầu mọi dự án đổi sang phiên bản ví dụ.

Cấu trúc:

~~~text
lifecycle-demo/
  settings.gradle
  build.gradle
  gradlew                  # do gradle wrapper tạo và lưu vào repo
  gradlew.bat
  gradle/wrapper/...
  src/main/java/com/example/lifecycle/LifecycleApplication.java
  src/test/java/com/example/lifecycle/LifecycleApplicationTest.java
~~~

### 7.1. Định nghĩa build

`settings.gradle`:

~~~groovy
rootProject.name = 'lifecycle-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Java plugin cung cấp `classes`/`test` và nối `jar` vào `assemble`, `test` vào `check`. Spring Boot plugin cung cấp `bootJar` và nối nó vào `assemble`. Dependency management phối hợp với Spring Boot plugin để lấy các phiên bản dependency đồng bộ; `starter-web` cung cấp web runtime và `starter-test` cung cấp công cụ test. Cần có Gradle Wrapper tương thích với phiên bản plugin và JDK 17 được cài đặt hoặc cấp qua toolchain; các file Wrapper phải được tạo/lưu trong dự án theo quy trình của nhóm.

`src/main/java/com/example/lifecycle/LifecycleApplication.java`:

~~~java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`src/test/java/com/example/lifecycle/LifecycleApplicationTest.java`:

~~~java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleApplicationTest {
    @Test
    void pingMethodReturnsExpectedText() {
        assertEquals("pong", new LifecycleApplication().ping());
    }
}
~~~

Test trên là **unit test trực tiếp của method `ping()`**: nó xác nhận output của method, **không xác minh HTTP request mapping, Spring context hay packaged runtime**. Nhờ vậy bài tập cố tình tách biệt trách nhiệm `test` với `assemble` và phép smoke test cuối cùng.

### 7.2. Chạy lần lượt và ghi điều quan sát được

**Bước A — `classes`:**

~~~bash
./gradlew clean classes
~~~

Kỳ vọng: `compileJava`/`processResources` (nếu có source/resource) và `classes` thành công; main class được sinh trong `build/classes/java/main/`. Chưa có lý do để khẳng định đã chạy test hoặc tạo executable JAR.

**Bước B — `test`:**

~~~bash
./gradlew test
~~~

Kỳ vọng: Gradle chuẩn bị `testClasses` và chạy đúng **một** test JUnit trong ví dụ (trừ khi project có test khác hoặc cấu hình thay đổi). Report cho thấy test `pingMethodReturnsExpectedText` thành công. Nếu `compileJava` hoặc `classes` hiện `UP-TO-DATE`, đó là kết quả tối ưu hợp lệ.

**Bước C — `check`:**

~~~bash
./gradlew check
~~~

Kỳ vọng: `check` yêu cầu `test`; các test có thể `UP-TO-DATE` vì vừa chạy ở B. Không phát sinh thêm static analysis gate khi build file mẫu chưa khai báo plugin/ràng buộc tương ứng.

**Bước D — `assemble`:**

~~~bash
./gradlew assemble
~~~

Kỳ vọng: `jar`/`bootJar` được xử lý theo Spring Boot plugin; có executable JAR ở `build/libs/`. Bài này chưa dùng `assemble` để chứng minh test đạt. Kiểm tra nội dung bằng `jar tf`; chọn JAR **không có classifier `-plain`** (nếu giữ convention mặc định).

**Bước E — `build`:**

~~~bash
./gradlew build
~~~

Kỳ vọng: Gradle coi cả `check` và `assemble` là dependency. Vì B–D vừa tạo kết quả, nhiều task có thể `UP-TO-DATE`; đây không phải bằng chứng chúng bị bỏ qua trái phép.

**Bước F — xác minh artifact chạy thật:**

~~~bash
java -jar build/libs/lifecycle-demo-0.0.1-SNAPSHOT.jar --server.port=8085
~~~

Ở terminal thứ hai, sau khi startup thành công:

~~~bash
curl -i http://localhost:8085/ping
~~~

Kỳ vọng: HTTP status `200` và **response body `pong`**. Những dòng HTTP header, log, thứ tự task, thời gian build là phụ thuộc môi trường nên không đưa ra “stdout chính xác” cố định. Dừng server bằng Ctrl+C. Nếu `8085` đã bị chiếm, chọn cổng trống và dùng cùng cổng trong lệnh gọi.

Kết luận theo từng bước: sau A biết main đã biên dịch; sau B biết test đơn vị mẫu đã đạt; sau C biết các task verification được đăng ký đã đạt; sau D có artifact; sau E cả verification và packaging đã đạt theo cấu hình; sau F có thêm bằng chứng **chính artifact đó chạy và phục vụ HTTP**. Các bằng chứng này bổ trợ, không thay thế nhau.

### 7.3. Thử nghiệm có kiểm soát để chứng minh quan hệ

Sửa **tạm thời** assertion trong test từ `assertEquals("pong", ...)` thành `assertEquals("pang", ...)`, giữ nguyên mã production. Sau đó:

~~~bash
./gradlew test
./gradlew check
./gradlew assemble
./gradlew build
~~~

Kỳ vọng về **trạng thái logic**, với project mặc định ở ví dụ:

- `test` **FAIL** vì expected `pang` khác actual `pong`.
- `check` **FAIL** vì phụ thuộc test.
- `assemble` có thể **PASS**, vì chỉ cần biên dịch/đóng gói main output, không phụ thuộc test.
- `build` **FAIL** vì nhánh `check` thất bại, kể cả khi `bootJar` đã tồn tại từ trước hoặc có thể được tạo.

Thử thêm một lần khác: tạo lỗi cú pháp trong `LifecycleApplication.java` (ví dụ thiếu dấu đóng ngoặc) rồi gọi `classes`. Khi `compileJava` thất bại, cả các task cần main output sẽ bị ảnh hưởng; không cần đoán lỗi chỉ từ tên task cấp cao. **Khôi phục mã và assertion gốc sau thử nghiệm** để bài tập trở lại trạng thái pass.

## 8. Cách đọc task graph và log một cách chính xác

Từ thư mục dự án đã có Gradle Wrapper:

~~~bash
./gradlew tasks --all
./gradlew help --task build
./gradlew build --dry-run
./gradlew build --console=plain
~~~

- `tasks --all` hiển thị các task có thể gọi, bao gồm task ẩn/không nhóm; danh sách phụ thuộc plugin và module.
- `help --task build` cung cấp mô tả của task được đăng ký.
- `build --dry-run` cho thấy task được lên lịch và quan hệ thứ tự quan sát được trong cấu hình hiện tại; **không thực thi kiểm chứng**.
- `build --console=plain` giúp đọc log ở CI/terminal không có rich progress, nhận biết lỗi đầu tiên rõ hơn.

Dấu trạng thái thường gặp:

| Trạng thái | Cách hiểu đúng |
| --- | --- |
| Không kèm nhãn và có output task | Task đã được thực thi theo điều kiện thực tế của Gradle. |
| `UP-TO-DATE` | Input/output không thay đổi theo cơ chế incremental, nên Gradle dùng output trước. |
| `FROM-CACHE` | Output được khôi phục từ build cache hợp lệ theo key của task. |
| `NO-SOURCE` | Task không tìm thấy input nguồn để làm việc; cần kiểm tra nếu bạn mong có Java/test/resource. |
| `SKIPPED` | Task bị bỏ qua do cấu hình/điều kiện hoặc vì đang dry-run; xem nguyên nhân trước khi coi là thành công. |
| `FAILED` | Task thất bại; lần chạy hiện tại không thể được tính là PASS cho gate chứa task đó. |

**Đừng nhầm log của task tổng hợp với công việc thực tế.** Ví dụ `:classes`, `:check` hoặc `:assemble` có thể là task lifecycle gần như không có action, nhưng các dependency phía dưới thực hiện biên dịch/test/package.

### Multi-project và CI

Nếu repository có nhiều subproject, chạy `./gradlew build` tại root có thể tác động nhiều project. Để xem chính xác module ứng dụng, dùng task path đầy đủ:

~~~bash
./gradlew :app:classes
./gradlew :app:test
./gradlew :app:check
./gradlew :app:assemble
./gradlew :app:build --dry-run
~~~

`:app` ở đây là **tên subproject minh họa**; thay bằng path thực lấy từ `./gradlew projects`. Các dependency giữa module có thể khiến task ở module khác được kéo vào. CI nên chỉ rõ task/module và lưu test report/artifact, thay vì coi một dòng xanh ở root đủ xác nhận từng module.

## 9. Những hiểu nhầm và cách chẩn đoán

| Nhận định hoặc triệu chứng | Sai ở đâu? | Cách xác minh |
| --- | --- | --- |
| “`classes` xanh nên có file JAR để deploy.” | `classes` chuẩn bị output; packaging là `jar`/`bootJar`. | Kiểm tra `build/libs` và chạy đúng task package. |
| “`test` đã chạy nên toàn bộ integration test đã chạy.” | `test` mặc định chỉ bao trùm test nó được cấu hình nhận diện; integration task riêng không tự được thêm. | Xem task graph, report và liên kết `check`. |
| “`check` tự chạy mọi scanner cài trong project.” | Chỉ các verification task thực sự gắn vào đồ thị mới chạy. | `check --dry-run`, build script và plugin docs. |
| “`assemble` thành công nghĩa là tất cả test PASS.” | Hai nhánh package và verification độc lập theo cấu hình Java plugin mặc định. | Gây một test fail có kiểm soát và so sánh `assemble`/`check`. |
| “`build` có nghĩa compile → test → package theo đúng thứ tự này.” | Gradle dùng DAG; `assemble` và `check` là nhánh sibling; không có thứ tự tuyến tính bắt buộc. | `build --dry-run` và dependency rules. |
| “Có hai JAR thì lấy file nhỏ hơn/đầu tiên.” | Plain JAR thường không chứa Boot launcher/runtime dependency. | Kiểm tra tên classifier, manifest, `BOOT-INF` và `java -jar`. |
| “`BUILD SUCCESSFUL` tức mọi test đã chạy lại.” | Có thể `UP-TO-DATE`/cache, skip hoặc không có test. | Đọc test report, status và cấu hình task. |
| “`build` luôn bắt đầu bằng `clean`.” | `clean` là task riêng. | So sánh `build --dry-run` và `clean build --dry-run`. |
| “`-x test` là tối ưu vô hại trong CI.” | Loại trừ test task có thể làm `check`/`build` xanh khi verification quan trọng bị bỏ qua. | Chỉ dùng skip flag khi có chính sách, xem pipeline gate. |
| “`build` thành công nghĩa là app có thể chạy production.” | Build không tự thử port, profile, DB, secret, container và smoke behavior. | Chạy đúng artifact trên môi trường mục tiêu và thử một hành vi cốt lõi. |

**Cách xử lý lỗi theo tầng:**

1. Lỗi `compileJava`/`classes`: xem Java syntax, JDK/toolchain, annotation processor, generated sources, resource path.
2. Lỗi `compileTestJava`/`test`: xem test dependency, JUnit engine, fixture, assertion, classpath, report.
3. Lỗi task chạy dưới `check`: tìm tên verification task cụ thể và quy tắc gate; không sửa `check` chỉ để che lỗi.
4. Lỗi `jar`/`bootJar`: xem main class, Spring Boot plugin, duplicate resource, classifier, dependency runtime, archive task.
5. Lỗi `build`: truy về **task con đầu tiên báo FAILED**; tên `build` chỉ là đầu mối tổng hợp.
6. Lỗi `java -jar` sau build xanh: xem JDK runtime, manifest, dependency, profile/port/config và service phụ thuộc; đây là lớp kiểm chứng khác compile/package.

Không dùng `-x test` hoặc `enabled = false` để “sửa” bài test hỏng; đó là thay đổi phạm vi xác minh, không phải sửa nguyên nhân.

## 10. Checklist kết thúc bài và tự đánh giá

Một người học hiểu đúng năm task khi thực hiện được cả **giải thích lẫn kiểm chứng** sau:

- [ ] Nêu đúng nguồn tạo `classes`/`test` (Java plugin) và khung `check`/`assemble`/`build` (Base plugin và các plugin nối vào).
- [ ] Vẽ đúng hai nhánh của `build`: `check -> test` và `assemble -> jar/bootJar` (theo cấu hình).
- [ ] Giải thích `classes` tạo main output nhưng không chứng minh test hay package.
- [ ] Giải thích `testClasses` hỗ trợ `test` và report cho biết test nào thực sự được chạy.
- [ ] Xác nhận `check` chỉ bao phủ các verification task đã được đăng ký vào graph.
- [ ] Phân biệt `jar` plain với `bootJar` executable và xác định file dùng để chạy.
- [ ] Chạy `build --dry-run` để xem task graph, không xem dry-run là test result.
- [ ] Tạo một test fail để chứng minh `check`/`build` fail trong khi `assemble` có thể pass.
- [ ] Đọc đúng `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `NO-SOURCE` và `FAILED`.
- [ ] Chạy executable JAR và làm một smoke test thay vì suy ra runtime từ `BUILD SUCCESSFUL`.

**Bài tập nộp:** kèm bảng năm dòng cho `classes`, `test`, `check`, `assemble`, `build`, mỗi dòng ghi (1) lệnh đã gọi, (2) task con quan sát được từ `--dry-run`/log, (3) output hoặc report, (4) điều đã chứng minh, (5) điều còn chưa chứng minh. Đính kèm tên executable JAR và kết quả `GET /ping`. Kết luận đầy đủ phải nêu được vì sao `assemble` và `check` là hai trục trách nhiệm khác nhau cùng hợp thành `build`.

## Tài liệu tham khảo chính thức

- [Gradle Java Plugin — source set và lifecycle tasks](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Base Plugin — assemble, check, build](https://docs.gradle.org/current/userguide/base_plugin.html)
- [Gradle — Task Basics và dependency graph](https://docs.gradle.org/current/userguide/task_basics.html)
- [Gradle — Controlling Task Execution: dependsOn, mustRunAfter, shouldRunAfter](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3.13/gradle-plugin/packaging.html)

Các ví dụ giả định Gradle Wrapper hoạt động, dependency được tải được và JDK tương thích. Khi áp dụng vào dự án thực tế, **dùng task graph và build script thực tế làm căn cứ cuối cùng** vì plugin và cấu hình riêng có thể thay đổi quan hệ mặc định.