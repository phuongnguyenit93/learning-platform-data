# Phân biệt gradle.properties, local.properties và tệp cấu hình tự định nghĩa

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Cấu trúc dự án

## Mục tiêu học tập

Sau bài học, bạn có thể giải thích vì sao ba nhóm tệp có đuôi .properties trông giống nhau nhưng có cơ chế hoạt động khác nhau; chọn đúng nơi lưu cấu hình chung, cấu hình theo máy và cấu hình do ứng dụng hoặc script tự đọc; biết cách Gradle tìm project property, hiểu các nguồn có thể ghi đè giá trị; và chạy một dự án Java 17 chứng minh sự khác biệt bằng kết quả thực tế.

**Ý chính:** Tên tệp không làm phát sinh hành vi một cách thần kỳ. Gradle có cơ chế nhận diện **gradle.properties**; **local.properties** là quy ước được công cụ Android sử dụng, không phải tệp cấu hình mặc định của Gradle Core cho mọi dự án; còn **tệp tự định nghĩa** chỉ có tác dụng khi build script, plugin hoặc chương trình chủ động đọc và áp dụng nội dung.

## 1. Đặt ba tệp vào cấu trúc dự án

Một dự án Java dùng Gradle có thể có cấu trúc như sau:

~~~text
properties-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── local.properties                 # chỉ có ý nghĩa khi công cụ/script sử dụng
├── config/
│   └── build-options.properties     # do dự án tự định nghĩa
├── gradle/
│   └── wrapper/
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
└── src/
    └── main/java/demo/ConfigDemo.java

GRADLE_USER_HOME/
└── gradle.properties                # cấu hình ở mức người dùng/máy
~~~

Các mục có hậu tố .properties trong sơ đồ **không cùng vai trò**:

- settings.gradle quyết định tên build và các project tham gia; build.gradle cấu hình plugin, dependency và task.
- gradle.properties dùng để cung cấp thiết lập Gradle hoặc project properties mà Gradle biết cách tìm.
- local.properties có thể do Android Studio hoặc một hệ thống nội bộ tạo ra để lưu đường dẫn trên máy người phát triển.
- config/build-options.properties là tên do nhóm tự chọn; Gradle không tự hiểu các key trong đó.
- gradle/wrapper/gradle-wrapper.properties xác định thông tin bản phân phối **Gradle Wrapper** (như distributionUrl). Dù cùng đuôi .properties, đây là một tệp riêng thuộc Wrapper; không thể dùng thay gradle.properties.

Cả ba nhóm tệp chính thường sử dụng định dạng key=value, có thể có dòng chú thích bắt đầu bằng #, nhưng **cú pháp giống nhau không tạo ra cơ chế nạp giống nhau**.

## 2. Bảng đối chiếu nhanh

| Tiêu chí | gradle.properties | local.properties | Tệp tự định nghĩa, ví dụ config/build-options.properties |
|---|---|---|---|
| Ai nhận diện? | Gradle Core có cơ chế tìm và nạp | Android Gradle Plugin/Android Studio theo quy ước; Gradle Core nói chung không tự nạp | Chỉ code hoặc plugin được dự án cấu hình để nạp |
| Vị trí thường gặp | Build root, GRADLE_USER_HOME; có thể có Gradle installation | Thường ở root của dự án Android | Vị trí tùy nhóm chọn, nên rõ ràng và nhất quán |
| Thường chứa | org.gradle.*, systemProp.*, project property | sdk.dir, cmake.dir và các đường dẫn/cài đặt Android theo máy | Cờ tùy biến, tên sản phẩm, cấu hình công cụ riêng, đường dẫn file do logic build yêu cầu |
| Có tự tác động đến build? | Một số key có ý nghĩa trực tiếp với Gradle; các key tự đặt chỉ có hiệu lực khi code/plugin dùng | Chỉ nếu Android tooling hoặc build logic sử dụng | Không, phải khai báo cách đọc và cách áp dụng |
| Có nên commit? | **Có thể commit** file của dự án nếu chứa cấu hình chung, không có secret | Dự án Android thường **không commit** vì chứa đường dẫn máy riêng | Tùy bản chất: commit cấu hình chung; bỏ qua file máy riêng/secret |
| Khi giá trị khác theo môi trường? | Dùng project property từ CLI, user home, environment hoặc CI secret store | Android tooling tự tìm đường dẫn theo máy; không dùng cho key tùy ý của Android | Thiết kế quy tắc override, default và kiểm tra thiếu file rõ ràng |
| Trường hợp điển hình | Bật build cache, đặt JVM args, cấu hình tham số plugin | Android SDK path trên từng máy | Cấu hình build báo cáo, quy tắc code generation hoặc dữ liệu đầu vào cho task riêng |

Không nên phân loại bằng đuôi file hoặc vị trí đơn lẻ. Cần hỏi **ai đọc tệp**, **đọc lúc nào**, **key nào được hiểu**, **mức ưu tiên ra sao**, và **có được đưa lên Git hay không**.

## 3. gradle.properties: cấu hình mà Gradle biết cách tìm

### 3.1. Những nhóm giá trị thường đặt trong gradle.properties

Ví dụ file tại root dự án:

~~~properties
# Cấu hình hoạt động của Gradle
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8

# Project property: chỉ phát huy tác dụng khi script/plugin sử dụng
app.banner=Hello from gradle.properties

# Ví dụ truyền Java system property cho tiến trình Gradle
systemProp.example.buildMode=debug
~~~

Cần phân biệt ba loại giá trị:

1. **Gradle property**, thường có tiền tố org.gradle.: Gradle hiểu để cấu hình daemon, cache, parallelism hoặc tính năng của Gradle. Ví dụ org.gradle.caching=true có thể bật build cache; kết quả cache vẫn phụ thuộc điều kiện của task.
2. **Project property**, ví dụ app.banner: Gradle cung cấp giá trị cho project/build logic, nhưng tự nó không đổi nội dung ứng dụng. Script hoặc plugin phải truy xuất và dùng giá trị.
3. **System property** qua tiền tố systemProp.: Gradle chuyển phần sau tiền tố thành Java system property cho JVM chạy Gradle. Nó **không mặc nhiên** trở thành system property của một ứng dụng Java chạy trong JVM khác, chẳng hạn tiến trình của task run hoặc test; phải truyền vào tiến trình đó theo cấu hình phù hợp.

Một sai lầm phổ biến là nghĩ ghi app.banner=... vào gradle.properties sẽ làm System.getProperty("app.banner") trong Main.java tự có giá trị. Không có cơ chế tổng quát như vậy: project property của Gradle và system property của chương trình Java là hai vùng cấu hình khác nhau.

### 3.2. Gradle tìm tệp ở đâu?

Gradle có thể đọc gradle.properties từ các nguồn chuẩn, nổi bật là:

- **GRADLE_USER_HOME/gradle.properties**: cấu hình theo người dùng, mặc định thường là ~/.gradle/gradle.properties trên Unix/macOS hoặc thư mục .gradle trong user profile trên Windows. GRADLE_USER_HOME có thể được cấu hình khác.
- **Build root/gradle.properties**: cấu hình chia sẻ cho build cụ thể; đây là vị trí nhóm thường đưa vào Git.
- **Gradle installation/gradle.properties**: cấu hình từ bản cài đặt Gradle nếu áp dụng; ít là nơi nhóm chủ động chỉnh sửa.

Với **Gradle properties**, cấu hình ở user home có độ ưu tiên cao hơn cấu hình cùng tên tại build root, và build root cao hơn Gradle installation. Flag tương ứng trên CLI có thể được ưu tiên cao hơn các file.

Không nên tự giả định rằng tệp gradle.properties ở mọi thư mục con của multi-project đều được providers.gradleProperty() đọc như cấu hình root. Tài liệu Gradle hiện hành phân biệt nguồn được Provider API dùng với tra cứu project property động bằng findProperty/property. Đối với cấu hình dùng chung, cách dễ bảo trì là đặt ở **build root** và dùng rõ ràng một API truy xuất có chủ đích.

### 3.3. Đọc project property bằng Provider API

Trong build.gradle (Groovy DSL):

~~~groovy
def banner = providers.gradleProperty('app.banner')
    .orElse('Hello, default')

tasks.register('showBanner') {
    doLast {
        println banner.get()
    }
}
~~~

- providers.gradleProperty('app.banner') trả về Provider, cho phép biểu diễn giá trị có thể xuất phát từ nhiều nguồn Gradle và kết hợp lazy.
- orElse(...) là fallback khi project property không tồn tại.
- get() chỉ lấy giá trị khi được yêu cầu; trong ví dụ nhỏ này nó nằm trong action của task. Với build logic lớn, nên nối Provider vào thuộc tính đầu vào của task để khai báo input rõ ràng, hỗ trợ caching và configuration cache phù hợp.
- Nếu dùng property('app.banner') thay vì Provider, giá trị thiếu có thể gây ngoại lệ; findProperty(...) có thể trả null. Tránh truy cập giá trị không kiểm soát.

Nếu tệp root chứa app.banner=Hello from gradle.properties và không có nguồn ưu tiên cao hơn, gọi task trên sẽ in nội dung đó.

### 3.4. Độ ưu tiên khi cùng một project property xuất hiện ở nhiều nơi

Đối với **project property được cung cấp cho build ở phạm vi chung** và truy xuất qua providers.gradleProperty(), thứ tự các loại nguồn thường là:

1. Tham số CLI -Pkey=value.
2. Java system property có tên org.gradle.project.key, có thể đặt bằng -Dorg.gradle.project.key=value.
3. Environment variable có tiền tố ORG_GRADLE_PROJECT_, ví dụ ORG_GRADLE_PROJECT_appBanner=... để cung cấp tên key appBanner.
4. gradle.properties của Gradle user home.
5. gradle.properties của build root.
6. gradle.properties của bản cài Gradle.

Ví dụ với key app.banner, CLI dùng:

~~~bash
./gradlew showBanner -Papp.banner="Hello from CLI"
~~~

Giá trị CLI sẽ thắng giá trị app.banner trong tệp root. Với environment variable, nên chọn tên property phù hợp cách truyền bằng ORG_GRADLE_PROJECT_ và kiểm tra môi trường CI/shell thực tế; tên có dấu chấm có thể khó thao tác trong tên biến môi trường. Chẳng hạn nên dùng key appBanner nếu dự định truyền thường xuyên qua ORG_GRADLE_PROJECT_appBanner.

**Đừng nhập nhằng thứ tự trên với mọi loại cấu hình:** org.gradle.* có quy tắc flag/property riêng; Java system property -Dkey cũng không tương đương mọi project property -Pkey. Ngoài ra, code tự đọc một file khác và tự đặt thứ tự override sẽ không tự tuân theo thứ tự Gradle.

## 4. local.properties: quy ước theo môi trường, nổi bật trong Android

### 4.1. local.properties không phải “gradle.properties thứ hai”

Một dự án Java thuần dùng Gradle **không mặc nhiên tải root/local.properties**. Nếu tạo file:

~~~properties
app.banner=Hello from local.properties
~~~

thì providers.gradleProperty('app.banner') **không tự nhận** giá trị này chỉ nhờ tên file. Nếu bạn thấy local.properties ảnh hưởng đến một dự án Java thuần, hãy tìm code hoặc plugin đã chủ động nạp file đó.

Với dự án **Android**, Android Studio và Android Gradle Plugin có quy ước riêng để quản lý thiết lập theo máy. Ví dụ một local.properties của dự án Android có thể chứa:

~~~properties
# Ví dụ minh họa cho máy của từng lập trình viên
sdk.dir=/home/developer/Android/Sdk
~~~

Tùy môi trường, có thể gặp cmake.dir, ndk.symlinkdir hoặc các khóa Android được công cụ hỗ trợ. Một số khóa cũ như ndk.dir đã bị đánh dấu deprecated, vì thế cần đối chiếu tài liệu Android hiện hành. Các đường dẫn trong ví dụ là giả định, không phải đường dẫn dùng chung cho mọi máy.

**Lưu ý quan trọng cho Android:** Tài liệu Android coi local.properties là nơi dành cho các thuộc tính phục vụ Android Gradle Plugin. Không nên tự nhét những khóa tùy biến của công ty vào đó; hãy dùng tệp cấu hình riêng nếu cần. Hướng dẫn Android cũng khuyến nghị loại local.properties khỏi source control.

### 4.2. Vì sao thường không commit local.properties?

Đường dẫn SDK hay toolchain giữa Windows, Linux, macOS và CI không giống nhau. Nếu commit một đường dẫn cố định như /home/developer/Android/Sdk, máy khác khó áp dụng và có thể nhận lỗi khi build.

Một .gitignore điển hình cho dự án Android có thể chứa:

~~~gitignore
/local.properties
~~~

Điều này là **quy ước quản lý file của dự án**, không phải Gradle tự động bí mật hóa nội dung. Nếu file đã từng được commit, thêm vào .gitignore không tự xóa file khỏi lịch sử Git hoặc khỏi bản theo dõi hiện có; cần xử lý riêng và tuyệt đối không đưa secret lên repository.

Cũng không nên khẳng định mọi dự án dùng tệp tên local.properties đều thuộc Android: nhóm hoàn toàn có thể tự viết loader dùng tên ấy trong một dự án khác, nhưng đó là **quy ước của nhóm**, không phải Gradle Core.

## 5. Tệp cấu hình tự định nghĩa: quyền chủ động thuộc về build logic

Tên tệp có thể là config/build-options.properties, build-settings.yml, config/ci.json hoặc bất kỳ tên hợp lý nào. Gradle không tự đọc chỉ vì tệp tồn tại. Nếu muốn sử dụng, bạn phải:

1. Đặt vị trí rõ ràng tương đối với project hoặc build root.
2. Chọn format và cơ chế parse đúng, ví dụ java.util.Properties cho .properties hoặc plugin/library cho YAML/JSON.
3. Định nghĩa điều gì xảy ra khi file thiếu, sai cú pháp hoặc thiếu key.
4. Gắn giá trị vào task/plugin cần sử dụng và mô tả thứ tự override.
5. Xác định file nào là cấu hình chung được commit, file nào là bản local bị bỏ qua và cách CI nhận giá trị.

Ví dụ tệp config/build-options.properties:

~~~properties
app.region=ap-southeast-1
report.enabled=true
~~~

Muốn lấy app.region, code có thể dùng Provider API để đọc nội dung file:

~~~groovy
def regionProvider = providers
    .fileContents(layout.projectDirectory.file('config/build-options.properties'))
    .asText
    .map { raw ->
        def props = new java.util.Properties()
        props.load(new java.io.StringReader(raw))
        props.getProperty('app.region', 'unknown')
    }
    .orElse('unknown')
~~~

Đây là **mã trong build.gradle**, không phải tệp cấu hình độc lập. Phần fileContents nhận file do dự án chọn, asText cung cấp nội dung dạng văn bản, map parse theo quy tắc java.util.Properties, còn orElse cho giá trị mặc định nếu file không có nội dung được cung cấp. Nếu file có nhưng sai định dạng hoặc loader gặp lỗi, việc dùng fallback không có nghĩa lỗi luôn bị nuốt; cần sửa lỗi thực tế.

Khi giá trị của file được đọc trong pha configuration, nó có thể là đầu vào cấu hình và ảnh hưởng khả năng dùng lại configuration cache; khi Provider được nối vào input của task, file/giá trị có thể được theo dõi ở đúng phạm vi task. Với build logic phức tạp hoặc định dạng riêng, cần thiết kế các thuộc tính task và input/output rõ ràng. Đừng đọc file trong task một cách âm thầm rồi tuyên bố build cache luôn hợp lệ.

## 6. Thực hành đầy đủ: thấy rõ ai đọc tệp nào

Đây là ví dụ **Gradle Groovy DSL + Java 17**. Mục tiêu là để Gradle đọc project property từ gradle.properties, script chủ động đọc một tệp tự định nghĩa và truyền cả hai giá trị vào ứng dụng Java. Không cần Android để chạy ví dụ.

### 6.1. Các file của ví dụ

~~~text
properties-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── config/
│   └── build-options.properties
└── src/main/java/demo/ConfigDemo.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'properties-demo'
~~~

**gradle.properties**

~~~properties
# Một Gradle property được Gradle hiểu
org.gradle.caching=true

# Một project property do demo sử dụng
app.banner=Hello from gradle.properties
~~~

**config/build-options.properties**

~~~properties
app.region=ap-southeast-1
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.ConfigDemo'
}

// Gradle tìm project property bằng cơ chế có sẵn.
def bannerProvider = providers.gradleProperty('app.banner')
    .orElse('Hello, default')

// File riêng: build script chủ động chọn file và parse.
def regionProvider = providers
    .fileContents(layout.projectDirectory.file('config/build-options.properties'))
    .asText
    .map { raw ->
        def props = new java.util.Properties()
        props.load(new java.io.StringReader(raw))
        props.getProperty('app.region', 'unknown')
    }
    .orElse('unknown')

// task run có nhờ plugin application.
// Chuyển hai giá trị sang JVM đang chạy chương trình Java.
tasks.named('run') {
    systemProperty 'demo.banner', bannerProvider.get()
    systemProperty 'demo.region', regionProvider.get()
}
~~~

**src/main/java/demo/ConfigDemo.java**

~~~java
package demo;

public final class ConfigDemo {
    private ConfigDemo() {
    }

    public static void main(String[] args) {
        System.out.println("banner=" + System.getProperty("demo.banner"));
        System.out.println("region=" + System.getProperty("demo.region"));
    }
}
~~~

Các file Groovy và Java trên tạo thành một dự án có thể chạy trên môi trường dùng JDK 17 và một bản Gradle tương thích. Plugin application tạo task run; plugin Java được nó áp dụng để biên dịch ứng dụng. Java toolchain yêu cầu JDK 17 phù hợp cho công việc Java. Nếu chưa có JDK phù hợp hoặc chưa cấu hình cách tải toolchain, Gradle có thể báo lỗi môi trường.

**Vì sao đoạn build script này đọc được cấu hình?**

- bannerProvider dùng providers.gradleProperty: Gradle tự tìm giá trị app.banner trong các nguồn project property chuẩn.
- regionProvider dùng providers.fileContents: chính build script đã chỉ định config/build-options.properties; tên file tự nó không có quyền năng đặc biệt.
- systemProperty trên task run là **bước nối tường minh** từ cấu hình build sang JVM ứng dụng. Nếu không nối, System.getProperty("demo.banner") và System.getProperty("demo.region") sẽ không nhận hai giá trị này chỉ vì file .properties nằm ở root.
- Để ví dụ dễ đọc, Provider được lấy giá trị bằng get() lúc cấu hình task run. Ở build lớn cần tối ưu configuration cache và tính incremental, ưu tiên xây task có Property/Provider đầu vào được khai báo và nối lười thay vì tự đọc file tùy tiện.

### 6.2. Chạy lệnh và kiểm tra stdout

Nếu dự án đã có Gradle Wrapper, dùng:

~~~bash
./gradlew -q run
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
~~~

Với đúng các file minh họa, không có property override và không có lỗi môi trường, **hai dòng do chương trình Java in ra** là:

~~~text
banner=Hello from gradle.properties
region=ap-southeast-1
~~~

Giờ thử ghi đè app.banner bằng tham số CLI:

~~~bash
./gradlew -q run -Papp.banner="Hello from CLI"
~~~

Đầu ra của chương trình đổi thành:

~~~text
banner=Hello from CLI
region=ap-southeast-1
~~~

Điều này chứng minh -P thay giá trị **project property**, trong khi app.region vẫn đến từ **file tự định nghĩa** do build script đã nạp. Nếu bạn tạo thêm một root/local.properties chứa app.region=another-region trong dự án Java thuần này, kết quả **không đổi**, vì ví dụ không có code đọc local.properties.

Muốn thử thay đổi file tự định nghĩa, sửa config/build-options.properties thành app.region=eu-west-1 rồi chạy lại. Dòng region khi đó là region=eu-west-1. Muốn thử fallback, xóa file tùy biến trong môi trường thí nghiệm; regionProvider có orElse('unknown') nên chương trình có thể nhận region=unknown, miễn những bước khác trong build không yêu cầu file đó.

Nếu chưa có Wrapper, cần một lần khởi tạo bằng một Gradle đã cài hoặc công cụ khởi tạo dự án:

~~~bash
gradle wrapper
~~~

Sau đó sử dụng các script gradlew/gradlew.bat và đưa Wrapper cần thiết vào Git. Lần đầu Wrapper có thể cần mạng để tải Gradle distribution nếu cache chưa có. Không nên sửa tay nội dung gradle/wrapper/gradle-wrapper.properties để lưu các key app.banner/app.region: nó là tệp phục vụ Wrapper.

### 6.3. Thêm lớp override có chủ đích cho file riêng

Giả sử CI cần đặt region mà không sửa config/build-options.properties. Bạn có thể thiết kế **quy tắc của riêng dự án** bằng cách thay định nghĩa regionProvider bằng:

~~~groovy
def fileRegion = providers
    .fileContents(layout.projectDirectory.file('config/build-options.properties'))
    .asText
    .map { raw ->
        def props = new java.util.Properties()
        props.load(new java.io.StringReader(raw))
        props.getProperty('app.region', 'unknown')
    }

def regionProvider = providers.gradleProperty('app.region')
    .orElse(fileRegion)
    .orElse('unknown')
~~~

Lúc này thứ tự do **build script quy định** là: project property app.region (chẳng hạn -Papp.region=eu-west-1), sau đó giá trị từ file config/build-options.properties, cuối cùng là unknown. Việc ưu tiên -P so với file tự định nghĩa là do dòng orElse(fileRegion) bạn viết, không phải Gradle âm thầm nạp mọi file .properties rồi gộp chúng.

Tuy nhiên, cần thống nhất key và tránh hai nguồn cấu hình trùng tên mà không ai biết nguồn nào được ưu tiên. Một sơ đồ override đơn giản, được tài liệu hóa, sẽ dễ bảo trì hơn việc thêm hàng loạt fallback không rõ ràng.

## 7. Quản lý version control, môi trường và bí mật

Một quy ước dễ áp dụng:

| Nơi đặt | Nên chứa | Chính sách chia sẻ |
|---|---|---|
| Root gradle.properties | Thiết lập Gradle chung và project property không nhạy cảm | Commit để đồng đội và CI dùng cấu hình thống nhất |
| GRADLE_USER_HOME/gradle.properties | Tùy chỉnh theo tài khoản/máy, ví dụ cấu hình local được phép | Giữ ngoài Git của dự án |
| Android local.properties | Đường dẫn Android SDK/CMake hoặc thiết lập local mà Android tooling yêu cầu | Đưa vào .gitignore; không chia sẻ đường dẫn máy |
| config/build-options.properties | Cấu hình build công khai, ổn định, có version | Commit nếu mọi môi trường cần cùng giá trị |
| config/build-options.local.properties | Giá trị riêng theo máy nếu **build script đã định nghĩa cách nạp** | Ignore; có thể commit file ví dụ .example với giá trị giả |
| CI environment/secret manager | Token, password, signing credential | Cấp lúc chạy qua cơ chế bảo mật, không ghi vào repo hoặc log |

Không nên lưu mật khẩu thật vào bất cứ file nào định commit, kể cả gradle.properties. Đối với CI, có thể cung cấp project property nhạy cảm qua biến môi trường ORG_GRADLE_PROJECT_<tênKey>, hoặc một secret store tích hợp với pipeline. Cần tránh in giá trị nhạy cảm, truyền secret trực tiếp trên CLI nếu có nguy cơ lộ trong lịch sử shell/process list, hoặc vô tình đưa secret vào báo cáo/cache của build.

**Phân biệt cấu hình build và cấu hình ứng dụng chạy thật:** Gradle có thể dùng config để quyết định biên dịch/test/đóng gói. Trong ứng dụng Spring Boot, application.properties hoặc application.yml thường là cấu hình runtime được Spring Boot đọc theo cơ chế của framework, không phải đồng nghĩa với gradle.properties. Build thành công cũng không chứng tỏ các biến môi trường production của ứng dụng đã sẵn sàng.

## 8. Lỗi thường gặp và cách truy nguyên

### Trường hợp 1: Đã sửa local.properties nhưng Gradle vẫn dùng giá trị cũ

Nếu đó là dự án Java không có Android plugin, kiểm tra script có đọc local.properties thật không. Với Android, kiểm tra key bạn dùng có thuộc danh sách Android hỗ trợ, đường dẫn đúng và file đang ở project root phù hợp. Đừng mặc định local.properties sẽ ghi đè gradle.properties.

### Trường hợp 2: Sửa root gradle.properties mà giá trị không đổi

Kiểm tra có -P trên CLI, -Dorg.gradle.project.<key>, ORG_GRADLE_PROJECT_<key> hoặc GRADLE_USER_HOME/gradle.properties ghi đè không. Tên key có phân biệt chữ hoa/chữ thường, ký tự dấu chấm và cách hệ điều hành truyền environment variable cần được kiểm tra cẩn thận. Đừng sửa file khác trước khi xác định **API nào đọc giá trị**.

### Trường hợp 3: Tưởng project property tự xuất hiện trong Java main

System.getProperty() của ứng dụng đọc Java system properties của JVM ứng dụng. Nếu cần truyền giá trị từ Gradle vào task run/test, cấu hình task tương ứng, ví dụ systemProperty. Nếu cần config runtime sau khi đã đóng gói, dùng cơ chế môi trường, command-line args hoặc cấu hình runtime mà ứng dụng hỗ trợ. Đừng giả định giá trị từ build script tự đi vào JAR.

### Trường hợp 4: Tệp riêng thay đổi nhưng task không chạy lại

Rà soát nơi đọc file và cách khai báo đầu vào. Một task đọc file ngoài luồng mà không khai báo input có thể khiến quyết định UP-TO-DATE/build cache sai. Prefer Provider API và input/output model của Gradle cho logic build tùy biến. Nếu giá trị được lấy trong configuration, chú ý tác động đến configuration cache.

### Trường hợp 5: Dùng chung một tên key ở nhiều cấp

Ví dụ app.region được đặt trong file tùy biến, project property và CI. Nếu script không ghi rõ ưu tiên, kết quả dễ khó đoán. Chọn một quy ước đơn nhất, ghi tài liệu thứ tự ưu tiên và có cách quan sát an toàn cho giá trị **không nhạy cảm**.

### Trường hợp 6: Copy file local từ máy này sang máy khác

Cấu hình path như sdk.dir, JDK path, cache path phụ thuộc máy và OS. Không dùng đường dẫn tuyệt đối của một máy làm mặc định cho cả nhóm. Cấp dependency/toolchain bằng công cụ có cơ chế resolve phù hợp và đặt đường dẫn local đúng phạm vi.

## 9. Cách quyết định nên dùng tệp nào

Bạn có thể áp dụng các câu hỏi theo thứ tự:

1. **Đó có phải cấu hình Gradle đã hỗ trợ sẵn?** Ví dụ org.gradle.caching hoặc org.gradle.jvmargs: cân nhắc gradle.properties của dự án hoặc người dùng.
2. **Đó là project property mà build script/plugin đã chấp nhận?** Dùng gradle.properties, -P hoặc nguồn property chuẩn; truy xuất qua providers.gradleProperty.
3. **Đó là đường dẫn Android SDK theo máy?** Theo tài liệu Android dùng local.properties cho key được hỗ trợ; không chia sẻ file local trên Git.
4. **Đó là cài đặt riêng của nhiệm vụ build?** Chọn một tệp có tên rõ ràng, viết loader và quy tắc override, khai báo input của task thích hợp.
5. **Đó là cấu hình lúc ứng dụng đang chạy?** Xem cơ chế cấu hình runtime của chính ứng dụng/framework; chỉ dùng Gradle để cấp giá trị nếu workflow thực sự yêu cầu.
6. **Có dữ liệu nhạy cảm hay khác nhau theo CI/máy?** Dùng secret manager hoặc kênh cấu hình cục bộ được kiểm soát; tránh commit và log.

## 10. Bài tập tự kiểm tra

**Bài 1.** Trong dự án Java không dùng Android, bạn tạo local.properties chứa cacheEnabled=true nhưng không viết loader. Build có tự bật cache không?

**Bài 2.** root/gradle.properties có app.banner=Root; GRADLE_USER_HOME/gradle.properties có app.banner=User; CLI chạy -Papp.banner=CLI. providers.gradleProperty('app.banner') trả về gì?

**Bài 3.** Bạn cần lưu đường dẫn Android SDK của từng máy. Chọn file nào, có đưa vào Git không, và vì sao?

**Bài 4.** Nhóm định nghĩa config/quality.properties cho ngưỡng kiểm tra. Nếu không có code đọc và áp dụng ngưỡng, liệu file có thay đổi task check không?

**Bài 5.** Task test Java cần nhận region từ một project property. Có thể dùng System.getProperty('region') trong unit test ngay sau khi thêm region=... vào gradle.properties mà không cấu hình task test không?

**Đáp án gợi ý:**

1. Không; Gradle Core không tự nạp local.properties và cache thực sự được Gradle cấu hình qua các cơ chế như org.gradle.caching.
2. CLI, vì -P có độ ưu tiên cao hơn các nguồn Gradle project property còn lại.
3. Với Android, dùng local.properties cho sdk.dir theo quy ước công cụ và ignore khỏi Git; đường dẫn cụ thể khác nhau giữa máy/CI.
4. Không; file tự định nghĩa cần được build logic/plugin đọc, có thứ tự override và áp dụng vào task.
5. Không mặc định; cần truyền thuộc tính sang JVM của test task, hoặc cung cấp config runtime theo cách unit test chủ động đọc.

## Tài liệu chính thức

- [Gradle User Manual — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): các loại property, nguồn và độ ưu tiên.
- [Gradle User Manual — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): đọc giá trị lazy và nối Provider/Property vào task.
- [Gradle User Manual — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): cách đọc file và environment trong build logic, ảnh hưởng đến cache.
- [Android Developers — Configure your build](https://developer.android.com/build): local.properties và các key phục vụ Android tooling.
- [Android Developers — Android build structure](https://developer.android.com/build/android-build-structure): ý nghĩa file và khuyến nghị loại local.properties khỏi source control.

**Ghi nhớ:** Hãy chọn tệp dựa trên **cơ chế đọc và nơi tiêu thụ cấu hình**. gradle.properties thuộc cơ chế property của Gradle; local.properties chỉ có ý nghĩa trong công cụ/quy ước cụ thể, nổi bật là Android; tệp tự định nghĩa cần loader, default, chính sách override và quản lý an toàn.