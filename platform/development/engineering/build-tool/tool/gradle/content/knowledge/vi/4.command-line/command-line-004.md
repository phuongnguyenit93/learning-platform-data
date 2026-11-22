# Gradle CLI: phân biệt `clean`, `check`, `assemble` và `build` theo plugin

## 1. Mục tiêu và điểm mấu chốt

Bốn tên `clean`, `check`, `assemble` và `build` thường xuất hiện trong một dự án Gradle, nhưng **chúng là tên task do plugin cung cấp/cấu hình**, không phải bốn thao tác cố định áp dụng y hệt cho mọi mã nguồn. Plugin quyết định task nào tồn tại, task nào được nối vào task nào và sản phẩm cuối cùng là gì.

Sau bài này, bạn có thể:
- Chọn đúng lệnh khi chỉ muốn xóa output, chỉ muốn kiểm tra chất lượng, chỉ muốn đóng gói hoặc muốn thực hiện build đầy đủ.
- Phân biệt **lifecycle task** (task điều phối) với **task thực thi** (biên dịch, chạy test, tạo JAR/ZIP...).
- Giải thích vì sao cùng `gradlew build` nhưng một dự án Java, một ứng dụng và một project chỉ dùng Base plugin có kết quả khác nhau.
- Đọc task graph và nhận ra test, kiểm tra tĩnh, coverage, phân phối ứng dụng được tích hợp vào build hay chưa.
- Dùng task path đúng trong build nhiều project và tránh suy luận sai từ dòng `BUILD SUCCESSFUL`.

**Quy ước lệnh:** Chạy từ thư mục gốc có Gradle Wrapper. Linux/macOS: `./gradlew`; Windows PowerShell: `.\gradlew.bat`. Nếu chưa có Wrapper, có thể dùng Gradle đã cài để tạo nó bằng `gradle :wrapper`, rồi sử dụng Wrapper cho các lần chạy tiếp theo.

## 2. Task và plugin: tại sao tên giống mà việc làm khác?

Plugin `base` tạo các lifecycle task chuẩn. Plugin `java` tự áp dụng Base plugin rồi móc các task Java vào; `java-library` kế thừa hành vi Java; `application` cũng áp dụng Java và Distribution plugin. Các plugin kiểm tra chất lượng như Checkstyle có thể nối thêm task kiểm tra vào `check`.

**Lifecycle task** thường chỉ có ý nghĩa ở *các task mà nó phụ thuộc* (`dependsOn`). Nó không nhất thiết chứa hành động biên dịch/kiểm thử/đóng gói trong chính task đó. Khi chạy `build`, Gradle dựng đồ thị phụ thuộc và thực thi những task cần thiết để hoàn thành `build`.

Đồ thị **khái niệm** với Java plugin:

~~~text
                  build
                 /     \
            assemble   check
               |         |
              jar       test
               |         |
             classes  testClasses
                 \      /
               compileJava ...
             
clean  (task riêng, KHÔNG phải dependency mặc định của build)
~~~

Đây là hình giản lược để thấy mối quan hệ; thực tế `test` còn cần classpath và các task biên dịch/copy resource phù hợp. **Không mặc định `assemble` phải chạy trước `check` hoặc ngược lại**: hai nhánh không có quan hệ thứ tự trực tiếp, Gradle sắp xếp theo dependency graph và thông tin về input/output.

## 3. So sánh nhanh bốn task

| Task | Ý nghĩa chuẩn từ Base plugin | Trong dự án Java thông thường | Điều **không** nên suy ra |
| --- | --- | --- | --- |
| `clean` | Xóa thư mục output `layout.buildDirectory` của project (mặc định là `build/`) | Xóa các sản phẩm biên dịch, JAR, report... nằm trong build directory | Không xóa source, không xóa dependency cache của Gradle, không tự chạy `build` |
| `check` | Điểm gom tác vụ **xác minh** chất lượng | Java plugin nối `test`; plugin khác có thể thêm lint/static analysis | Không tự tạo JAR vì ý nghĩa của `check` là kiểm tra; cũng không đồng nghĩa mọi loại test đã được cấu hình |
| `assemble` | Điểm gom tác vụ **tạo sản phẩm** để sử dụng/phân phối | Java plugin nối `jar`; Application/Distribution plugin có thể thêm ZIP/TAR | Không mặc định chạy test hoặc đảm bảo sản phẩm có chất lượng |
| `build` | Lifecycle task phụ thuộc **`check` và `assemble`** | Tập hợp kiểm thử/xác minh và sản phẩm từ các plugin đang áp dụng | Không tự deploy, publish, chạy app hay xóa sạch output trước |

**Tóm quan hệ:** `build = check + assemble` ở cấp task dependency; đây **không phải phép cộng hai câu lệnh shell chạy tách biệt**. `clean` độc lập. Thực tế các nhánh có thể dùng chung task `classes`, nên Gradle không cần biên dịch cùng một đầu vào hai lần chỉ vì `build` có hai dependency.

### 3.1. `clean` — dọn output, không dọn toàn bộ hệ thống

Với Base plugin, `clean` là task kiểu `Delete`, xóa **build directory của project**; đường dẫn có thể được đổi bằng `layout.buildDirectory`. Trong một build nhiều project, mỗi project có build directory riêng. Lệnh task selector `clean` từ root có thể chọn các `clean` tương ứng trong cây project; còn `:app:clean` chỉ đích danh project `:app`.

~~~bash
./gradlew clean
./gradlew clean build
~~~

Hai lệnh không tương đương: lệnh đầu chỉ dọn; lệnh sau yêu cầu dọn rồi build. `build` không tự gọi `clean`. Gradle tôn trọng thứ tự an toàn được yêu cầu ở `clean build`, nên `clean` không thể xóa sản phẩm vừa được `build` tạo.

Sau `clean`, build kế tiếp thường tốn công biên dịch lại vì các output đã bị xóa. Nhưng dependency được tải về trong Gradle user home (thường `~/.gradle/caches`), dữ liệu source, VCS và các output bên ngoài build directory **không tự biến mất**. Vì thế:
- `clean` không phải lệnh “xóa mọi cache”, cũng không thay `--refresh-dependencies`.
- Không cần chạy `clean` trước mọi `build`; Gradle có cơ chế kiểm tra up-to-date và build cache.
- Không nên dùng `clean` như cách chữa mọi lỗi dependency hoặc lỗi cấu hình.

### 3.2. `check` — xác minh theo những gì đã được nối vào

Base plugin cho `check` một điểm tập hợp các tác vụ verification. **Bản thân Base plugin không tạo test Java**. Khi áp dụng `java`, `check` sẽ phụ thuộc vào `test`. Khi áp dụng Checkstyle trong dự án Java, `check` có thể gọi thêm `checkstyleMain` và `checkstyleTest`. Các bộ kiểm thử bổ sung, kiểm tra coverage hoặc task tự tạo **chỉ tham gia `check` nếu plugin hoặc build script thực sự kết nối chúng**.

~~~bash
./gradlew check
./gradlew check --dry-run
~~~

`--dry-run` hiển thị các task dự định được yêu cầu/chạy nhưng **không thực thi hành động của task**. Sử dụng nó để kiểm chứng `check` có nối đến `test`, `checkstyleMain`... hay không; đừng coi `--dry-run` là kiểm thử thành công.

Quan trọng: `check` có thể kích hoạt `compileJava` và `compileTestJava` gián tiếp để test chạy được. “`check` không đóng gói” **không có nghĩa** “`check` không biên dịch”.

### 3.3. `assemble` — tạo artifact, không thay thế kiểm thử

Base plugin tạo lifecycle task `assemble` và cho plugin khác gắn nhiệm vụ tạo sản phẩm. Với Java plugin, `assemble` phụ thuộc `jar`; `jar` lại cần `classes`, nên Gradle biên dịch mã rồi tạo JAR khi cần.

~~~bash
./gradlew assemble
./gradlew assemble --dry-run
~~~

Với Java plugin, sản phẩm thường ở `build/libs/`. `assemble` **không mặc định phụ thuộc `test`**: việc tạo được JAR không chứng minh test chạy hoặc đỗ. Nếu dùng `application`, còn có các gói phân phối ZIP/TAR do Distribution plugin nối vào `assemble`.

### 3.4. `build` — tổng hợp artifact và verification

Base plugin định nghĩa `build` phụ thuộc `check` và `assemble`. Với Java, điều này thường gồm cả `test` và `jar`. Nếu các plugin khác gắn task vào hai nhánh đó, `build` bao gồm chúng một cách tự nhiên.

~~~bash
./gradlew build
./gradlew build --dry-run
~~~

Gradle **không tự hiểu** kiểm thử tích hợp, kiểm tra bảo mật, Docker image, code coverage, upload artifact, triển khai production... phải nằm trong `build`. Chúng chỉ xuất hiện khi được plugin hoặc build script gắn vào đồ thị. Nếu test thất bại, `build` thất bại; không được giả định artifact đã/ chưa tạo xong tại thời điểm lỗi vì thứ tự hai nhánh không cố định.

## 4. Ý nghĩa đổi theo plugin

| Plugin ở project | `clean` | `check` | `assemble` | `build` |
| --- | --- | --- | --- | --- |
| `base` | Xóa build directory | Có sẵn điểm móc verification; mặc định chưa có test Java | Có sẵn điểm móc artifact; mặc định chưa có JAR | Phụ thuộc hai lifecycle task `check` và `assemble`; có thể gần như không làm gì nếu không gắn task |
| `java` | Như Base | Gọi `test`, kèm những kiểm tra được gắn thêm | Gọi `jar` (và artifact bổ sung nếu cấu hình) | Bao gồm `check` và `assemble`, tức test và JAR trong cấu hình Java điển hình |
| `java-library` | Như Java | Kế thừa kiểm thử từ Java | Kế thừa JAR và có mô hình `api`/`implementation` cho thư viện | Như Java cộng các task được plugin khác nối thêm |
| `application` | Như Java | Kiểm tra Java như trên | JAR cùng các phân phối ZIP/TAR của Distribution plugin | Bao gồm kiểm tra và đóng gói ứng dụng; **không có nghĩa tự chạy task `run`** |
| `checkstyle` cùng `java` | Không thay ý nghĩa cơ bản | Nối thêm các task phân tích Checkstyle của các source set | Không biến `assemble` thành tác vụ kiểm tra | `build` sẽ bao gồm Checkstyle vì gọi `check` |
| `jacoco` cùng `java` | Không thay ý nghĩa cơ bản | **Không tự** nối `jacocoTestCoverageVerification` vào `check` | Không tự tạo report coverage qua `assemble` | Muốn chặn build theo coverage thì phải thiết lập rule và wiring phù hợp |

Lưu ý ở hàng `base`: một build chỉ áp dụng Base plugin có thể báo `BUILD SUCCESSFUL` nhưng **không có một test hay artifact nào**. Bốn tên task là **quy ước mở rộng của plugin**, không phải bằng chứng build đã đáp ứng yêu cầu chất lượng.

### 4.1. Java Library và Application: chọn đúng sản phẩm

- `java-library`: dành cho thư viện Java. `assemble` tạo JAR; `check` chạy những kiểm tra được cấu hình. Plugin này cho phép công bố dependency qua `api` khi public API của thư viện yêu cầu.
- `application`: dành cho ứng dụng JVM có main class. Plugin này áp dụng Java và Distribution plugin, tạo thêm `run`, `startScripts`, `distZip`, `distTar`, `installDist`. Các gói phân phối nối với `assemble`, vì vậy `build` cũng tạo chúng.
- `run` là **task riêng để chạy ứng dụng**; `build` không mặc định gọi `run`. `installDist` cũng là task riêng nếu muốn cài ứng dụng vào thư mục local để kiểm tra.

### 4.2. Checkstyle và JaCoCo: tránh suy luận “đã bật plugin thì check hết”

Checkstyle plugin gắn `checkstyleMain` và `checkstyleTest` vào `check` khi dùng với Java. Nhưng bạn phải cung cấp cấu hình Checkstyle thích hợp (mặc định ở `config/checkstyle/checkstyle.xml`) và xử lý lỗi quy tắc như một bước kiểm chứng thực sự.

JaCoCo lại có khác biệt đáng nhớ: `jacocoTestReport` không mặc định phụ thuộc `test`; `jacocoTestCoverageVerification` cũng **không mặc định** là dependency của `check`. Vì vậy chỉ thêm `id 'jacoco'` chưa thể kết luận `./gradlew build` sẽ chặn bản build khi coverage dưới ngưỡng. Cần cấu hình violation rules và gắn task verification vào `check` một cách chủ động.

## 5. Phòng thực hành: quan sát 4 lệnh trên cùng một dự án Java 17

### 5.1. Tạo dự án nhỏ

Ví dụ dùng **Gradle Groovy DSL**. Giữ Gradle Wrapper ở gốc dự án; nếu không có Wrapper, dùng Gradle đã cài để chạy `gradle :wrapper` một lần. Các file cần có:

~~~text
task-lifecycle-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/example/Calculator.java
    ├── main/java/example/App.java
    └── test/java/example/CalculatorTest.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'task-lifecycle-lab'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Các phiên bản JUnit chỉ dùng cho bài thực hành, không phải tuyên bố phiên bản mới nhất. Cần có JDK 17 được Gradle toolchain nhận diện (hoặc cơ chế tải toolchain được cấu hình) và mạng khi tải dependency lần đầu.

**`src/main/java/example/Calculator.java`:**

~~~java
package example;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int a, int b) {
        return a + b;
    }
}
~~~

**`src/main/java/example/App.java`:**

~~~java
package example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Kết quả: " + Calculator.sum(2, 3));
    }
}
~~~

**`src/test/java/example/CalculatorTest.java`:**

~~~java
package example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, Calculator.sum(2, 3));
    }
}
~~~

Ba file Java có package khớp với thư mục, dùng cú pháp hợp lệ với Java 17. Plugin `java` biên dịch được hai file nguồn, plugin test dùng JUnit Jupiter để chạy `CalculatorTest`. `main` được chạy độc lập sau khi build; `java` không tự cung cấp task `run`.

### 5.2. Đọc task graph trước khi chạy thật

~~~bash
./gradlew tasks --all
./gradlew assemble --dry-run
./gradlew check --dry-run
./gradlew build --dry-run
~~~

Mục tiêu quan sát (không phải bản sao nguyên văn log Gradle):
- `assemble` kéo `classes` và `jar`.
- `check` kéo `test`; `test` cần `testClasses`, nên cũng biên dịch mã và test khi cần.
- `build` có cả nhánh `assemble` và `check`.
- `clean` không tự xuất hiện trong `build --dry-run` vì `build` không phụ thuộc `clean`.

Số lượng, thứ tự và trạng thái task trên console còn tùy Gradle, plugin, source set và các tùy biến khác. Đừng học thuộc một danh sách task log cố định thay cho cách đọc quan hệ dependency.

### 5.3. Chạy từng lệnh và quan sát kết quả

~~~bash
./gradlew clean
./gradlew assemble
./gradlew check
./gradlew build
~~~

1. Sau `clean`, output trong `build/` của project được xóa. Nếu chưa có output, task vẫn có thể hoàn thành.
2. Sau `assemble`, kiểm tra thư mục `build/libs/` có JAR. Với ví dụ `java`, bước này không chủ động yêu cầu test.
3. Sau `check`, kiểm tra task `test` có được chạy hoặc xác định trạng thái `UP-TO-DATE`; kết quả test thường có tại `build/reports/tests/test/index.html` nếu test đã thực thi.
4. Sau `build`, kiểm tra tổng thể; những task đã chạy ở bước 2–3 có thể báo `UP-TO-DATE` vì input/output không đổi.

Chạy class Java bằng `java` để kiểm chứng output ứng dụng (sau khi đã chạy `assemble`, `build` hoặc `classes`):

~~~bash
java -cp build/classes/java/main example.App
~~~

**Stdout chính xác của chương trình Java:**

~~~text
Kết quả: 5
~~~

Các lệnh Gradle có thêm log task, thời gian và thông tin runtime khác nhau; không nên nhầm log `BUILD SUCCESSFUL` với stdout của `App`. Nếu muốn chạy qua Gradle, cần áp dụng plugin `application` và đặt `application.mainClass` đúng.

### 5.4. Thí nghiệm có kiểm soát: build artifact có thay được test không?

Trong **bản sao của dự án thực hành**, tạm sửa assertion ở `CalculatorTest` thành `assertEquals(6, Calculator.sum(2, 3));`, trong khi mã thật vẫn trả 5.

~~~bash
./gradlew assemble
./gradlew check
./gradlew build
~~~

Kỳ vọng:
- `assemble` vẫn có thể thành công vì nhánh tạo JAR **không mặc định chạy `test`**.
- `check` thất bại khi `test` chạy assertion sai.
- `build` thất bại vì phụ thuộc `check`, dù các task tạo artifact có thể hoàn tất hoặc chưa tùy lịch task.

Khôi phục `assertEquals(5, ...)` rồi chạy lại `./gradlew check`. **Đây là bằng chứng thực tế** cho ý nghĩa khác nhau của `assemble` và `check`.

## 6. Quan sát sự thay đổi khi đổi hoặc thêm plugin

### 6.1. Chỉ áp dụng Base plugin

Trong một dự án **thực hành riêng**, `build.gradle` có thể đơn giản là:

~~~groovy
plugins {
    id 'base'
}
~~~

Chạy `./gradlew tasks`, `./gradlew check`, `./gradlew assemble` và `./gradlew build`. Có các lifecycle task chuẩn, nhưng không có `compileJava`, `test` hoặc `jar` do Base plugin tự tạo. Nếu chưa thêm task tùy biến, việc báo build thành công không chứng minh mã Java đã được kiểm thử hay đóng gói.

### 6.2. Đổi dự án Java thành Application

Trong dự án phần 5, **thay** khối plugin và thêm cấu hình application (giữ nguyên toolchain, dependencies, test):

~~~groovy
plugins {
    id 'application'
}

application {
    mainClass = 'example.App'
}
~~~

Đây là đoạn thay thế `plugins { id 'java' }` cũ, không phải tệp build đầy đủ độc lập. `application` tự kéo Java plugin và Distribution plugin.

~~~bash
./gradlew run
./gradlew assemble
./gradlew build
./gradlew distZip
./gradlew installDist
~~~

`run` in `Kết quả: 5` từ ứng dụng; `assemble` sẽ đóng gói cả JAR và phân phối ZIP/TAR (đầu ra thường có ở `build/distributions/`); `installDist` tạo một thư mục cài ứng dụng (thường trong `build/install/`). `build` vẫn phụ thuộc `check` và `assemble` nhưng **không tự gọi `run` hoặc `installDist`**. Sự khác biệt đến từ plugin, không phải tên lệnh `build` thay đổi.

### 6.3. Tự nối một task kiểm tra vào `check`

Với dự án Java phần 5, thêm đoạn sau **vào cuối `build.gradle`** khi vẫn có Java plugin:

~~~groovy
tasks.register('verifyMainSource') {
    doLast {
        if (!project.file('src/main/java/example/App.java').isFile()) {
            throw new GradleException('Thiếu App.java')
        }
    }
}

tasks.named('check') {
    dependsOn tasks.named('verifyMainSource')
}
~~~

Giờ `./gradlew check` **và** `./gradlew build` đều yêu cầu `verifyMainSource`, còn `./gradlew assemble` không tự yêu cầu nó. Đây là cách mở rộng quy ước Gradle: **gắn kiểm tra vào `check`**. Task kiểm tra này chỉ minh họa kiểm tra tồn tại file, chưa thay thế kiểm thử hành vi.

Đối với artifact do task tùy biến tạo, nguyên tắc tương tự: nối task tạo artifact vào `assemble` thay vì nối tùy tiện trực tiếp vào `build`, để `assemble` và `build` cùng phản ánh sản phẩm cần phát hành.

## 7. Dùng lệnh trong build nhiều project

Giả sử `settings.gradle` có:

~~~groovy
rootProject.name = 'multi-task-lab'
include 'core', 'app'
~~~

Trong `core/build.gradle` có `java-library`, còn `app/build.gradle` có `application`. Khi đứng ở root:

~~~bash
./gradlew projects
./gradlew build
./gradlew :core:check
./gradlew :core:assemble
./gradlew :app:build
./gradlew :app:clean
./gradlew clean build
~~~

- `./gradlew build` là **task selector**: chọn các task `build` phù hợp ở root/các subproject bên dưới, nên giúp build nhiều project trong cùng cây.
- `:core:check` chỉ yêu cầu task verification của `:core` và những dependency cần thiết.
- `:core:assemble` tạo các artifact của `:core`, không mặc định kiểm thử `:app`.
- `:app:build` yêu cầu build của ứng dụng và các task dependency cần để build nó. **Không tự suy ra `:core:check` sẽ chạy** chỉ vì `:app` có dependency mã vào `:core`.
- `:app:clean` dọn build directory của riêng `:app`; nếu muốn dọn nhiều project từ root, dùng task selector `clean` phù hợp.

**Lưu ý:** Project dependency (`implementation project(':core')`) giúp Gradle lấy đúng output và thứ tự biên dịch cần thiết, nhưng nó không tự tạo một chính sách “kiểm thử mọi project phụ thuộc” khi chỉ gọi `:app:build`. Khi CI phải kiểm thử tất cả project, hãy chạy task phù hợp trên toàn build hoặc xác định rõ các task cần yêu cầu.

## 8. Đọc log và kiểm tra đúng task thực thi

Những lệnh hữu ích để không đoán mò:

~~~bash
./gradlew help --task build
./gradlew tasks --all
./gradlew check --dry-run
./gradlew assemble --dry-run
./gradlew build --info
./gradlew build --rerun-tasks
~~~

- `help --task build`: hỏi Gradle task đó thuộc project nào và dùng để làm gì.
- `tasks --all`: xem task khả dụng; sự hiện diện của task **chưa chắc** có dependency bạn mong muốn.
- `--dry-run`: xem kế hoạch thực thi không chạy hành động của task. Các task được liệt kê thường hiển thị `SKIPPED` do dry run; đây không phải dấu hiệu test bị lỗi.
- `--info`: xem thông tin chi tiết hơn về việc chọn task, cache, up-to-date và dependency.
- `--rerun-tasks`: buộc chạy lại những task trong đồ thị mà không cần xóa build directory như `clean`.

Các trạng thái thường gặp:

| Trạng thái | Cách hiểu đúng |
| --- | --- |
| `UP-TO-DATE` | Input/output theo khai báo cho phép Gradle bỏ qua hành động vì kết quả đang còn hiệu lực; thường là tối ưu bình thường |
| `FROM-CACHE` | Gradle phục hồi output task từ build cache thay vì thực thi lại hành động |
| `NO-SOURCE` | Task nguồn không có file đầu vào phù hợp; nếu là `test`, phải kiểm tra test thật sự được phát hiện hay chưa |
| `SKIPPED` | Task bị bỏ qua vì điều kiện, cấu hình hoặc chế độ chạy; tra log/task config để biết lý do |
| `FAILED` | Có task thất bại; cần đọc task path và nguyên nhân cụ thể, không mặc định lỗi ở `build` lifecycle |

Đặc biệt, `BUILD SUCCESSFUL` chỉ nói những **task đã được yêu cầu và chạy hợp lệ** đã hoàn thành. Nếu project chưa khai báo test, bộ kiểm thử không được phát hiện hoặc ai đó dùng `-x test`, kết quả thành công **không chứng minh chất lượng sản phẩm**.

### Các nhầm lẫn cần tránh

1. **“`build` luôn xóa build directory trước.”** Sai; muốn dọn, gọi `clean`. Dùng `clean build` khi thật sự cần build sạch.
2. **“`assemble` chạy đủ test.”** Sai trong cấu hình Java chuẩn. `assemble` thiên về sản phẩm; `check` thiên về xác minh.
3. **“`check` luôn kiểm tra bảo mật, integration test và coverage.”** Sai; chỉ chạy task được nối vào `check`, trực tiếp hoặc qua plugin.
4. **“`build` đồng nghĩa chạy ứng dụng.”** Sai; muốn chạy với Application plugin thì dùng `run`.
5. **“Thêm JaCoCo là `build` tự chặn coverage thấp.”** Sai; task kiểm chứng coverage phải được cấu hình và nối vào `check`.
6. **“`clean` xóa cache dependency và sửa được mọi lỗi.”** Sai; clean chỉ xử lý output của project theo cấu hình.
7. **“`:app:build` luôn chạy `:core:check`.”** Sai; cần phân biệt project dependency phục vụ biên dịch với chính sách chạy verification của từng project.
8. **“`build -x test` vẫn xác minh toàn bộ test.”** Sai; `-x test` loại task `test` được chỉ định. Không dùng đó như bằng chứng test đã qua.

## 9. Checklist và bài luyện

### Chọn lệnh theo nhu cầu

| Cần làm gì? | Lệnh khởi đầu | Điều cần xác minh |
| --- | --- | --- |
| Dọn output trước khi phân tích lỗi sản phẩm cũ | `./gradlew clean` | Đường dẫn build directory cần dọn |
| Kiểm tra test/lint mà không yêu cầu đóng gói đầy đủ | `./gradlew check` | Các task đã gắn vào `check` |
| Tạo JAR/gói phân phối để thử nhanh | `./gradlew assemble` | Plugin, artifact và path đầu ra |
| Kiểm tra + tạo các artifact chuẩn | `./gradlew build` | Hai nhánh `check`/`assemble` và mọi kiểm tra cần thiết |
| Kiểm tra và đóng gói từ output mới | `./gradlew clean build` | Đúng thứ tự, chấp nhận chi phí rebuild |
| Chỉ build một project trong monorepo | `./gradlew :app:build` | Không bỏ sót test của các project khác nếu CI yêu cầu |

### Bài luyện tự kiểm tra

**Bài 1.** Một project chỉ áp dụng `base`, không task tự tạo. `./gradlew build` thành công. Có thể kết luận JUnit test đã chạy không? **Đáp án:** Không. Base plugin chỉ cung cấp lifecycle task; chưa có Java test.

**Bài 2.** Project `java` có test thất bại. Vì sao `assemble` có thể thành công nhưng `build` thất bại? **Đáp án:** `assemble` phụ thuộc `jar`, còn `build` phụ thuộc thêm `check`, và `check` phụ thuộc `test`.

**Bài 3.** Khi thay `java` bằng `application`, `assemble` có thể có thêm sản phẩm gì? **Đáp án:** Gói phân phối ứng dụng ZIP/TAR cùng script chạy, bên cạnh JAR.

**Bài 4.** Sau khi áp dụng JaCoCo, `check` đã tự chặn coverage dưới ngưỡng chưa? **Đáp án:** Chưa. Cần cấu hình `jacocoTestCoverageVerification` và nối nó vào `check`.

**Bài 5.** Trong build có `:core` và `:app`, muốn chạy verification toàn bộ project thì nên bắt đầu từ lệnh nào ở root? **Đáp án:** `./gradlew check` (task selector), rồi kiểm tra task graph của từng project; không coi `:app:check` là đương nhiên chạy `:core:check`.

**Tiêu chí hoàn thành:** Bạn tự vẽ được quan hệ `build -> {check, assemble}`, xác nhận được `jar`/`test`/`distZip` trong đồ thị theo plugin, biết vì sao `clean` độc lập và giải thích được đúng phạm vi của `:project:task`.

## Tài liệu chính thức để đối chiếu

- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): nguồn định nghĩa `clean`, `check`, `assemble`, `build`.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): task `jar`, `test` và liên kết lifecycle.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `distZip`, `distTar` và phân phối ứng dụng.
- [Gradle — Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html): kết nối kiểm tra chất lượng vào `check`.
- [Gradle — JaCoCo Plugin](https://docs.gradle.org/current/userguide/jacoco_plugin.html): coverage report và verification không tự thuộc `check`.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/gradle_command_line.html): task selector, `--dry-run`, `--rerun-tasks` và thứ tự an toàn.
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/intro_multi_project_builds.html): task name so với fully qualified task path.
