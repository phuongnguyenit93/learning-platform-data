# Các tác vụ biên dịch mã AOT và đưa tài nguyên sinh ra vào classpath trong Gradle

## 1. Mục tiêu và bối cảnh

Với module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng **Spring AOT** rồi biên dịch thành **GraalVM Native Image** nhằm đánh giá thời gian khởi động, mức dùng bộ nhớ và khả năng tương thích. Khi dùng Gradle, câu hỏi không chỉ là “chạy `nativeCompile` như thế nào”, mà còn là:

> Mã Java và tài nguyên do Spring AOT sinh ra được biên dịch, chuyển tiếp qua các tác vụ Gradle và đưa vào classpath dùng cho Native Image ra sao?

Hiểu luồng này giúp chẩn đoán ba nhóm vấn đề thường gặp:

- `processAot` không phân tích được ứng dụng tại **thời điểm build**;
- mã AOT đã được tạo nhưng **chưa biên dịch hoặc không đi vào classpath** của bước sau;
- ứng dụng native khởi động được nhưng thiếu **resource, reflection metadata hoặc hành vi truy cập động** khi chạy.

Spring AOT, Gradle và Native Image có trách nhiệm khác nhau: **Spring AOT** chuẩn bị mã và metadata dựa trên ngữ nghĩa Spring; **Gradle** điều phối việc tạo/biên dịch/copy những đầu ra đó; **GraalVM Native Image** tiêu thụ bytecode và metadata để tạo executable native.

## 2. Nhìn toàn bộ đồ thị tác vụ

Với dự án Spring Boot được cấu hình để hỗ trợ AOT/native, luồng khái niệm thường giống sơ đồ sau:

~~~mermaid
flowchart TB
    S["src/main/java và src/main/resources"] --> M["compileJava / processResources / classes"]
    M --> A["processAot: Spring phân tích cấu hình và bean"]
    A --> GS["Nguồn Java AOT được sinh"]
    A --> GR["Tài nguyên / metadata AOT được sinh"]
    GS --> CJ["compileAotJava"]
    GR --> PR["processAotResources"]
    CJ --> AC["aotClasses: đầu ra AOT đã chuẩn bị"]
    PR --> AC
    M --> NC["nativeCompile: GraalVM Native Image"]
    AC --> NC
    NC --> E["Executable native"]
~~~

**Lưu ý:** đây là biểu diễn *luồng phụ thuộc logic*, không phải bản chụp task graph cố định cho mọi phiên bản. Gradle và các plugin có thể thêm tác vụ, thay tên một số tác vụ trung gian hoặc tổ chức dependency khác nhau. Hãy dùng `./gradlew tasks --all` và `./gradlew ... --dry-run` để quan sát dự án thực tế.

Trong những cấu hình Gradle/Spring Boot phổ biến:

| Tác vụ hoặc nhóm tác vụ | Nhiệm vụ chính | Đầu ra cần quan tâm |
| --- | --- | --- |
| `compileJava` | Biên dịch mã Java ứng dụng | Các file `.class` của ứng dụng |
| `processResources` | Copy/xử lý resource từ `src/main/resources` | Resource thông thường trên classpath |
| `classes` | Tập hợp kết quả biên dịch và resource thông thường | Đầu vào ứng dụng đã chuẩn bị |
| `processAot` | Chạy Spring AOT trên ứng dụng đã có các đầu vào cần thiết | Mã Java AOT và tài nguyên/metadata AOT |
| `compileAotJava` | Biên dịch mã Java do AOT sinh ra | Bytecode của mã AOT |
| `processAotResources` | Xử lý/copy tài nguyên sinh bởi AOT | Tài nguyên AOT dùng trong classpath build |
| `aotClasses` | Tập hợp đầu ra class/resource AOT (nếu phiên bản plugin có task này) | Đầu ra AOT sẵn cho bước kế tiếp |
| `nativeCompile` | Gọi Native Image với classpath và cấu hình cần thiết | Executable theo OS/CPU đích |

**Không phải tất cả các tác vụ chạy tuần tự theo thứ tự trong bảng.** Gradle chỉ thực thi các tác vụ cần thiết theo dependency graph; một số công việc độc lập có thể chạy song song.

## 3. Cấu hình Gradle tối thiểu để phối hợp AOT và native

Giả sử dự án sử dụng **Gradle Groovy DSL** (`build.gradle`), có Java và Spring Boot. Plugin Native Build Tools cần được áp dụng nếu muốn có các task native như `nativeCompile`.

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<SPRING_BOOT_VERSION>'
    id 'org.graalvm.buildtools.native' version '<NATIVE_BUILD_TOOLS_VERSION>'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

test {
    useJUnitPlatform()
}
~~~

Hai chuỗi `<SPRING_BOOT_VERSION>` và `<NATIVE_BUILD_TOOLS_VERSION>` chỉ là **placeholder**: phải thay bằng các phiên bản tương thích và đang được dự án sử dụng trước khi chạy. Ở dự án quản lý version bằng `settings.gradle`, version catalog hoặc plugin management, có thể không cần ghi version trực tiếp trong đoạn `plugins`. Tùy cấu hình dự án, cơ chế quản lý BOM/dependency có thể cũng cần được thiết lập phù hợp.

Plugin **Spring Boot Gradle** tạo và cấu hình các tác vụ phục vụ ứng dụng, bao gồm AOT ở những phiên bản hỗ trợ. Plugin **GraalVM Native Build Tools** cung cấp việc tích hợp với GraalVM Native Image. Khi cả hai được cấu hình tương thích, quá trình native build sử dụng đầu ra AOT mà plugin Spring Boot chuẩn bị.

Kiểm tra bằng chính Gradle Wrapper của dự án:

~~~bash
# Liệt kê tác vụ, bao gồm các tác vụ ít hiển thị.
./gradlew tasks --all

# Quan sát task graph được lên kế hoạch, chưa thực thi build.
./gradlew nativeCompile --dry-run
~~~

Trên Windows, sử dụng `gradlew.bat`; các ví dụ shell ở đây dành cho Linux/macOS. Nếu `nativeCompile` không tồn tại, kiểm tra việc áp dụng `org.graalvm.buildtools.native` và tính tương thích plugin. Nếu `processAot` không tồn tại, kiểm tra plugin Spring Boot/version và cấu hình liên quan.

## 4. `processAot`: nơi Spring biến cấu hình thành mã và metadata

`processAot` là bước xử lý ứng dụng bằng Spring AOT **tại thời điểm build**. Ở mức khái niệm, nó quan sát classpath ứng dụng, cấu hình Spring, bean definitions và điều kiện liên quan để tạo mã khởi tạo và thông tin cần thiết cho môi trường native.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class BillingConfiguration {
    @Bean
    BillingService billingService(PaymentGateway paymentGateway) {
        return new BillingService(paymentGateway);
    }
}
~~~

Thông thường, khi chạy JVM, Spring có thể đọc cấu hình, tạo bean definition và tìm cách gọi factory method trong quá trình khởi động. Khi dùng AOT, Spring có thể sinh những đoạn mã Java phục vụ đăng ký/khởi tạo bean tương ứng; Spring vẫn tạo bean khi chương trình chạy theo lifecycle, nhưng bớt phần khám phá có thể làm trước.

Ngoài mã Java, quá trình AOT có thể cung cấp hoặc tổng hợp **runtime hints** cho các trường hợp như reflection, JDK dynamic proxy, resource và serialization. Những hints này giúp GraalVM Native Image giữ lại các khả năng truy cập động không đủ rõ qua phân tích bytecode thông thường.

Chạy riêng bước AOT:

~~~bash
./gradlew processAot
~~~

Ở các cấu hình Spring Boot Gradle thông dụng, thư mục sinh có thể gồm những đường dẫn dạng:

~~~text
build/
  generated/
    aotSources/             # Java source do Spring AOT sinh
    aotResources/           # Tài nguyên/metadata do AOT sinh
~~~

Đường dẫn chính xác là **chi tiết triển khai của phiên bản plugin**. Không hardcode chúng làm nguồn sự thật khi triển khai CI: có thể tìm kết quả thực tế trong `build/` hoặc kiểm tra task outputs của Gradle. Không nên sửa trực tiếp file generated vì lần build tiếp theo có thể ghi đè.

### Vì sao `processAot` có thể thất bại ngay cả khi `compileJava` thành công?

`compileJava` chủ yếu xác nhận mã nguồn có thể biên dịch. `processAot` phải xử lý **cấu hình Spring** và các thành phần cần thiết để chuẩn bị bean graph. Nó có thể gặp vấn đề khi:

- một điều kiện cấu hình phụ thuộc vào biến môi trường hoặc profile khác với dự kiến;
- mã khởi tạo bean hay một extension của framework cố thực hiện công việc chỉ hợp lý ở runtime;
- bean registration động không thể dự đoán trong giai đoạn AOT;
- dependency/plugin chưa hỗ trợ đúng AOT;
- tài nguyên hay thông tin cấu hình mà bước build cần không có sẵn.

Không nên giả định rằng các dịch vụ ngoài như database, broker hay API luôn phải chạy trong lúc AOT xử lý; điều đó phụ thuộc cách ứng dụng khởi tạo và thiết kế bean. Nếu quá trình AOT đang cố thực hiện công việc mạng không cần thiết, cần xem lại logic khởi tạo hơn là mặc định bật mọi dịch vụ bên ngoài trong CI.

### Cấu hình build time và runtime

Một số điều kiện quyết định **cấu trúc bean** có thể được đánh giá ở thời điểm AOT. Ví dụ, nếu cấu hình build khiến một bean không được đăng ký, không thể mặc định đổi biến môi trường khi chạy executable là bean ấy sẽ xuất hiện.

Ngược lại, các giá trị runtime thông thường như URL, timeout hoặc credential **không mặc nhiên bị đóng băng** chỉ vì dùng AOT. Cần phân biệt “giá trị được đọc lúc chạy” với “giá trị quyết định bean graph lúc build”.

## 5. `compileAotJava`: mã AOT phải thành bytecode trước khi Native Image dùng được

Đầu ra Java source từ `processAot` chưa đủ để GraalVM Native Image xây dựng ứng dụng. Gradle cần chuyển các file `.java` được sinh thành `.class`, trong bối cảnh có thể tham chiếu tới các kiểu từ mã nguồn ứng dụng và dependency.

Tác vụ `compileAotJava` (ở phiên bản plugin cung cấp task đó) xử lý bước này:

~~~bash
# Quan sát task biên dịch đầu ra AOT.
./gradlew compileAotJava
~~~

Classpath để **biên dịch mã AOT** thường cần mã ứng dụng đã biên dịch và các dependency tương ứng. Còn classpath của **Native Image** cần chứa cả mã ứng dụng lẫn các class AOT đã biên dịch. Đây là hai mục đích classpath khác nhau:

| Classpath | Dùng vào việc gì? | Thiếu đầu vào sẽ gây gì? |
| --- | --- | --- |
| Java compile classpath | Biên dịch mã nguồn ứng dụng | Lỗi thiếu symbol/type ở `compileJava` |
| AOT compile classpath | Biên dịch Java source do Spring AOT sinh | Lỗi thiếu class/symbol ở `compileAotJava` |
| Classpath cho AOT processing | Cho Spring nhìn thấy code, dependency và resource cần phân tích | Lỗi phân tích cấu hình/bean hoặc thiếu nguồn dữ liệu |
| Classpath cho native compilation | Cho Native Image phân tích bytecode, AOT output và metadata | Lỗi thiếu lớp, thiếu metadata hoặc sai hành vi của executable |

Với plugin chính thống đã được tích hợp đúng cách, Gradle thường quản lý quan hệ này thông qua các task/configuration/source set. Không cần dùng `files('build/generated/aotSources')` để gắn thủ công các thư mục generated vào mọi source set; dễ gây duplicate class hoặc phụ thuộc vào đường dẫn nội bộ không ổn định.

## 6. `processAotResources`: vì sao tài nguyên sinh ra phải được đưa vào classpath?

Một dự án Spring Boot có **hai nhóm tài nguyên** cần phân biệt:

1. **Resource ứng dụng**: ví dụ `src/main/resources/application.yml`, template, schema, message bundle; được xử lý qua `processResources`.
2. **Resource/metadata do AOT sinh**: có thể gồm cấu hình hay metadata cho quá trình khởi tạo Spring và Native Image; được xử lý qua luồng tài nguyên AOT như `processAotResources`.

Ví dụ minh họa đầu vào:

~~~text
src/main/resources/
  application.yml
  templates/invoice.txt
~~~

Đầu ra khái niệm sau khi xử lý:

~~~text
build/
  resources/
    main/                  # Resource thường của ứng dụng
    aot/                   # Resource AOT sau khi được xử lý (tùy plugin)
  classes/
    java/
      main/                # Bytecode ứng dụng
      aot/                 # Bytecode AOT (tùy plugin)
~~~

`processAotResources` đảm bảo các file tài nguyên được tạo ở giai đoạn AOT được đặt trong output resource tương ứng để **bước xử lý tiếp theo nhìn thấy được**. Với Gradle, các output đó tham gia vào classpath thông qua cấu hình task/source set thích hợp.

Điểm dễ nhầm: **một resource có trên build classpath không đồng nghĩa với việc nó chắc chắn nằm trong native executable**. Native Image xử lý resource theo cơ chế reachability/resource metadata; các file cần truy cập bằng tên động vẫn có thể phải được khai báo qua runtime hints hoặc metadata của thư viện.

### Ví dụ: khai báo resource mà ứng dụng thật sự cần

Giả sử lúc chạy, một service đọc template theo tên:

~~~java
try (InputStream in =
         getClass().getResourceAsStream("/templates/invoice.txt")) {
    if (in == null) {
        throw new IllegalStateException("Thiếu template invoice.txt");
    }
    // Đọc nội dung template và tạo hóa đơn...
}
~~~

Trong ứng dụng JVM, resource được chép bởi `processResources` có thể được tìm thấy trên classpath. Khi build native, cần bảo đảm template được đưa vào image. Nếu không có thư viện/framework nào cung cấp metadata thích hợp, có thể đăng ký:

~~~java
package com.example.invoice;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(InvoiceHints.class)
class InvoiceConfiguration {
}

class InvoiceHints implements RuntimeHintsRegistrar {
    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/invoice.txt");
    }
}
~~~

Ví dụ này giải quyết **hai điều kiện độc lập**:

- `src/main/resources/templates/invoice.txt` phải tồn tại và được đưa vào input classpath của build.
- Native Image phải có metadata/resource hints phù hợp để **đóng gói** resource ấy vào executable.

Nếu file không tồn tại từ đầu, thêm hint không tạo ra file. Nếu file tồn tại nhưng bị loại khỏi native image, chỉ kiểm tra `processResources` chưa đủ. Đó là lý do nên xác minh cả đầu ra Gradle và ứng dụng native chạy thật.

## 7. Các cấu hình classpath: hiểu trước khi tùy biến

Gradle quản lý classpath qua các **configuration** (như compile/runtime classpath) và output của **source set/task**. Khi plugin Spring Boot và Native Build Tools kết hợp, chúng gắn các đầu ra AOT đúng chỗ cho việc biên dịch native.

Những nguyên tắc giúp tránh lỗi:

- **Compile classpath** phục vụ biên dịch source; **runtime classpath** chứa những phần ứng dụng cần để chạy hoặc để công cụ phân tích lúc build.
- **Generated sources** cần được biên dịch trước khi đưa vào native compilation; đưa trực tiếp thư mục source Java vào một Java runtime classpath là chưa đủ.
- **Generated resources** cần được xử lý qua task resource để có mặt trên classpath thích hợp.
- **Native Image metadata** phải được công cụ nhìn thấy; không nên đoán rằng mọi file JSON/resource trên classpath đều tự được giữ lại trong binary.
- **Task dependencies** bảo đảm các output được sinh trước khi task downstream tiêu thụ. Không dùng thứ tự thủ công giữa các lệnh shell để thay thế dependency graph của Gradle.

Một số phiên bản plugin có các configuration/source set liên quan AOT (chẳng hạn configuration phục vụ compile/runtime AOT). Tên chính xác và quan hệ có thể thay đổi theo phiên bản, nên chỉ tùy chỉnh sau khi xem cấu hình/tài liệu plugin của bản đang dùng.

### Khi có generated source/resource từ công cụ khác

Giả sử dự án còn sinh Java từ OpenAPI hoặc sinh template từ một task riêng. Việc này khác với đầu ra Spring AOT:

1. Khai báo rõ **task tạo ra file** và thư mục output.
2. Gắn output vào source set hoặc input của task tiêu thụ thông qua cơ chế Gradle hỗ trợ, để Gradle quản lý dependency.
3. Đảm bảo file được sinh **trước** khi Spring AOT phân tích classpath nếu logic AOT phụ thuộc các file đó.
4. Với resource cần nằm trong native image, cấu hình resource hints khi cần.

Không tự copy toàn bộ `build/generated` vào `src/main/resources` hoặc thêm tất cả thư mục generated vào mọi classpath: điều này có thể gây trùng resource, giữ lại file không cần thiết và làm cache/incremental build khó dự đoán.

## 8. Thực hành: quan sát từng bước thay vì chỉ chạy `nativeCompile`

### Bước 1: kiểm tra task có tồn tại

~~~bash
./gradlew tasks --all
~~~

Tìm những task liên quan: `processAot`, `compileAotJava`, `processAotResources`, `aotClasses` và `nativeCompile`. Không ép phải xuất hiện tất cả nếu phiên bản plugin tổ chức task khác; dùng task graph thực tế làm căn cứ.

### Bước 2: chạy riêng AOT

~~~bash
./gradlew processAot
~~~

Kiểm tra:

- Log AOT có báo lỗi cấu hình bean, dependency hoặc điều kiện chạy ở build time không?
- Có mã Java và tài nguyên generated trong thư mục build tương ứng không?
- Nếu tạo file bằng một task khác, task đó có chạy trước AOT khi cần không?

Nếu `processAot` thất bại, chưa cần chuyển thẳng sang sửa `nativeCompile`; phải giải quyết nguyên nhân ở giai đoạn AOT.

### Bước 3: quan sát bước biên dịch và resource AOT

~~~bash
# Dùng khi những task này có trong phiên bản plugin đang sử dụng.
./gradlew compileAotJava processAotResources
~~~

Kiểm tra xem Java generated đã thành bytecode và các resource AOT đã được xử lý chưa. Nếu `compileAotJava` báo thiếu type, hãy xem classpath biên dịch AOT, dependency scope và mã generated. Nếu `processAotResources` không tạo được file cần thiết, xác định file có được sinh từ `processAot` không và task có input phù hợp không.

### Bước 4: xem Gradle sắp chạy gì khi build native

~~~bash
./gradlew nativeCompile --dry-run
~~~

`--dry-run` hiển thị những task được lên kế hoạch mà không thực thi phần build; dùng để thấy chuỗi AOT có được nối vào native compilation không. Chế độ này **không xác minh nội dung classpath hay khả năng link**. Cần thực thi build thật khi muốn kiểm tra kết quả cuối.

### Bước 5: build và chạy executable native

~~~bash
./gradlew nativeCompile
~~~

Vị trí executable thường ở:

~~~text
build/native/nativeCompile/
~~~

Tên binary có thể phụ thuộc plugin và tên dự án. Trên Windows có thể có phần mở rộng `.exe`. Kiểm tra log để phân biệt lỗi phát sinh trong AOT, Java compilation, Native Image analysis hay linker.

Sau đó chạy binary thực tế trên hệ điều hành/kiến trúc tương thích, thử ít nhất một HTTP endpoint cùng luồng có resource/reflection. Đây mới là bước kiểm chứng rằng generated source và resource đủ dùng ở runtime.

## 9. Kiểm thử native khác kiểm thử JVM ở đâu?

`./gradlew test` kiểm tra ứng dụng trong môi trường JVM thông thường. Nó rất cần thiết nhưng không đủ để xác nhận một executable native hoạt động đúng, vì JVM có thể truy cập những lớp và resource mà native image chưa được khai báo.

Native Build Tools thường cung cấp luồng **native test** như `nativeTest`; Spring Boot có thể hỗ trợ xử lý AOT riêng cho test, ví dụ task `processTestAot` ở những phiên bản thích hợp. Bản thân test native phải dùng đúng cấu hình và công cụ của dự án.

~~~bash
./gradlew test

# Khi plugin và bộ test hỗ trợ native test:
./gradlew nativeTest
~~~

Các testcase đáng ưu tiên gồm:

- Endpoint gọi service có AOP/proxy hoặc transaction.
- JSON binding/serialization với DTO thật.
- Load template, schema, file từ classpath.
- Gọi mã sử dụng reflection hoặc JNI.
- Các nhánh Spring configuration/profile/conditional được kỳ vọng trong bản build native.

Nếu test JVM pass nhưng native fail, xem lỗi ở thao tác động và metadata trước khi kết luận Gradle bỏ sót task. Nếu native build thậm chí không chứa class AOT hoặc resource generated, kiểm tra đầu ra và classpath/task graph trước.

## 10. Bảng chẩn đoán các vấn đề thường gặp

| Triệu chứng | Nơi kiểm tra | Cách xử lý phù hợp |
| --- | --- | --- |
| `Task 'processAot' not found` | Spring Boot Gradle plugin và phiên bản áp dụng | Kiểm tra `plugins`, phiên bản Spring Boot hỗ trợ AOT và danh sách task |
| `Task 'nativeCompile' not found` | GraalVM Native Build Tools plugin | Áp dụng plugin native tương thích, xác nhận task bằng `tasks --all` |
| `processAot` lỗi tạo ApplicationContext | Điều kiện/config và logic bean tại build time | Loại bỏ giả định runtime-only khỏi bước xử lý cấu hình hoặc cấp cấu hình build thích hợp |
| `compileAotJava` báo thiếu symbol | Source/bytecode ứng dụng, dependency và AOT compile classpath | Xem dependency scope, output `processAot` và mã được sinh |
| Native Image không nhìn thấy mã AOT | Task dependency/classpath đầu vào native | Xác nhận plugin được tích hợp, quan sát `--dry-run` và classpath theo task version |
| Tài nguyên có khi chạy JAR nhưng thiếu ở native | `processResources`, `processAotResources`, resource hints | Xác nhận file tồn tại trên build classpath và được đăng ký đưa vào native image |
| Reflection hoạt động trên JVM nhưng fail ở native | Runtime hints/reachability metadata | Khai báo class/thành viên cần truy cập, kiểm tra metadata do thư viện cung cấp |
| Mã generated trùng class hoặc resource | Tùy chỉnh source set và đường dẫn generated thủ công | Loại bỏ cấu hình thêm trùng; để plugin quản lý output AOT khi có thể |
| `nativeCompile` thất bại vì thiếu compiler/linker | JDK/GraalVM và native toolchain của OS | Cài và cấu hình `native-image`, compiler, SDK/linker phù hợp |
| Native chạy lỗi trên máy/container đích | OS/CPU/ABI và thư viện native | Build cho nền tảng đích; không dùng trực tiếp binary macOS trong Linux container |

### Trường hợp điển hình: “File có trong Gradle build nhưng native không tìm thấy”

Giả sử `src/main/resources/templates/invoice.txt` tồn tại, và `build/resources/main/templates/invoice.txt` cũng tồn tại sau `processResources`. Khi chạy JAR, `getResourceAsStream` đọc thành công; native executable lại trả `null`.

Đừng vội copy file vào các thư mục generated AOT. Trước hết cần kiểm tra **resource metadata** để Native Image đóng gói đúng file. Resource được Gradle đưa vào classpath ở build time và resource được Native Image đưa vào executable ở runtime là **hai điều kiện khác nhau**.

Ngược lại, nếu file không hề có trong output resource ở build time, một `RuntimeHintsRegistrar` đúng cũng không khôi phục được file bị thiếu. Khi đó phải kiểm tra `processResources` hoặc task tạo resource trong Gradle.

## 11. Classpath ở lúc build và lúc chạy: một khác biệt quyết định

Khi chạy JAR trên JVM, khái niệm **runtime classpath** gắn với classloader: `.class` và resource nằm trong JAR hoặc dependency có thể được tải khi chạy.

Với Native Image, **classpath ở bước native compilation** là đầu vào mà trình biên dịch phân tích. Executable được tạo ra **không vận hành như một JVM với classpath JAR có thể tùy ý mở rộng sau build**. Những class và resource cần cho executable phải được trình biên dịch nhìn thấy và giữ lại theo cơ chế tương ứng.

Vì vậy, cần xét ba câu hỏi độc lập:

1. **Đã sinh chưa?** `processAot` có tạo đúng Java source/metadata không?
2. **Đã đi vào đầu vào biên dịch chưa?** `compileAotJava`, `processAotResources` và các task liên quan có đóng góp output vào native compile classpath không?
3. **Đã được giữ trong binary chưa?** Native Image có biết về những class, resource và thành viên truy cập động qua reachability analysis/hints không?

Chỉ cần một bước thiếu, ứng dụng có thể build lỗi hoặc chạy native sai.

## 12. Checklist trước khi đo thời gian khởi động và bộ nhớ

Sau khi luồng Gradle/AOT hoàn chỉnh:

1. Chạy `./gradlew test` để có baseline JVM.
2. Chạy `./gradlew processAot` và xác nhận mã/tài nguyên được sinh.
3. Quan sát `nativeCompile --dry-run` để xác nhận kết nối task, rồi chạy build thật.
4. Chạy native executable và kiểm thử các nhánh có reflection, proxy, serialization, resource.
5. So sánh JAR JVM và native với **cùng endpoint, dữ liệu, CPU/RAM, cấu hình và tải**; đo thời gian sẵn sàng, RSS, độ trễ và thông lượng nếu cần.
6. Ghi lại **thời gian native build**, phiên bản Gradle/JDK/GraalVM/plugin và OS/CPU. Native có thể khởi động nhanh hoặc dùng ít bộ nhớ trong nhiều tình huống, nhưng kết quả cụ thể phải đo.
7. Nếu đóng gói container Linux, build bằng môi trường/builder phù hợp Linux và kiến trúc đích; không copy trực tiếp executable native macOS vào Linux image.

Ba điểm cần nhớ: **`processAot` tạo mã và metadata; Gradle biên dịch/copy đầu ra AOT rồi cung cấp classpath cho Native Image; Native Image tạo executable và quyết định những phần được giữ lại theo reachability/metadata.** Khi phân biệt đúng các tầng này, việc xử lý lỗi Gradle, AOT và resource sẽ rõ nguyên nhân hơn.
