# Đặt thuộc tính ở cấp dự án, người dùng và dòng lệnh

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Thuộc tính và môi trường

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ba phạm vi cấu hình quen thuộc của Gradle: **cấp dự án**, **cấp người dùng** và **mỗi lần gọi dòng lệnh**.
2. Phân biệt **Gradle properties** (cấu hình chính Gradle), **project properties** (giá trị cho build logic), **Java system properties** và **environment variables**.
3. Đặt project property vào root/gradle.properties, GRADLE_USER_HOME/gradle.properties, hoặc truyền qua -P, -Dorg.gradle.project.* và ORG_GRADLE_PROJECT_*.
4. Nêu đúng thứ tự ưu tiên khi nhiều nguồn đặt **cùng một project property**; nhận ra vì sao cấu hình của từng thành viên có thể ghi đè cấu hình đã commit.
5. Truy xuất giá trị bằng Provider API trong Groovy DSL, định nghĩa giá trị mặc định và truyền tường minh từ Gradle sang JVM của ứng dụng Java 17.
6. Giải quyết các tình huống thường gặp: cấu hình chạy đúng ở CI nhưng sai trên máy cá nhân, thiếu property, đặt nhầm JDK, xung đột tên biến và nguy cơ để lộ secret.

Bài học giới hạn ở **thuộc tính và phạm vi cấu hình build Gradle**. Một property được đọc trong build script không tự trở thành cấu hình của mọi tiến trình ứng dụng được đóng gói hoặc triển khai.

## 1. Vì sao phải phân chia phạm vi thuộc tính?

Giả sử nhóm cùng phát triển một ứng dụng Java:

- Mọi thành viên đều cần cùng thiết lập build cache và những giá trị mặc định phù hợp dự án.
- Mỗi người có thể dùng đường dẫn JDK, proxy hoặc cấu hình bộ nhớ Gradle khác nhau.
- Hệ thống CI phải truyền một tên môi trường hoặc build identifier cho **một lượt chạy cụ thể**, không cần sửa tệp trên Git.
- Có lúc một developer muốn tạm ghi đè giá trị để kiểm tra một trường hợp.

Nếu đặt tất cả cấu hình vào một tệp duy nhất rồi luôn chỉnh sửa trực tiếp, thay đổi riêng của máy có thể vô tình xuất hiện trong commit; CI thiếu đầu vào; hoặc lệnh của một người bị cấu hình cá nhân của người khác ghi đè. Gradle cho phép nhiều **nguồn cấu hình** để phân tách những nhu cầu đó.

Điểm cốt lõi cần hỏi trước khi viết:

> Thuộc tính này dùng để cấu hình **Gradle**, **project/plugin**, **JVM chạy Gradle**, hay **ứng dụng Java khi chạy**? Nó nên cố định cho cả nhóm, gắn với máy/người dùng, hay chỉ tồn tại trong một lần chạy?

## 2. Ba phạm vi bạn sẽ sử dụng thường xuyên

### 2.1. Cấp dự án: root/gradle.properties

Đặt file gradle.properties ở **thư mục gốc của build**, cùng cấp với settings.gradle và build.gradle. Đây là nơi lý tưởng cho giá trị mặc định **được phép chia sẻ** giữa các thành viên.

Ví dụ:

~~~text
sample-app/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
└── src/main/java/demo/Main.java
~~~

Nội dung root/gradle.properties:

~~~properties
# Thiết lập Gradle: hiệu lực theo cách Gradle định nghĩa
org.gradle.caching=true

# Project properties: chỉ có ý nghĩa nghiệp vụ nếu script/plugin đọc chúng
appMode=development
appLabel=Hello Project
~~~

- org.gradle.caching=true là **Gradle property**; Gradle hiểu để bật build cache khi đủ điều kiện.
- appMode=development và appLabel=Hello Project là **project properties**; chúng trở thành dữ liệu để build script hoặc plugin tiêu thụ.
- Nếu không có logic sử dụng appMode, việc thêm appMode=development không tự thay đổi chương trình Java hay tạo task mới.

**Khi nào commit file này?** Khi các thiết lập không nhạy cảm và nên áp dụng thống nhất cho nhóm. Không commit token, mật khẩu hoặc đường dẫn máy cá nhân. Khi file là nguồn thiết lập chung, version control giúp cùng commit mã cũng đi kèm cùng một cấu hình build mặc định.

### 2.2. Cấp người dùng: GRADLE_USER_HOME/gradle.properties

Gradle User Home chứa cache, init scripts, log và cấu hình theo người dùng. Vị trí mặc định thường là **~/.gradle** trên Linux/macOS hoặc thư mục **.gradle** dưới hồ sơ người dùng trên Windows. Biến môi trường GRADLE_USER_HOME hoặc cơ chế cấu hình tương ứng có thể thay đổi vị trí này.

Ví dụ file:

~~~text
~/.gradle/gradle.properties
~~~

Nội dung minh họa:

~~~properties
# Riêng cho người đang chạy Gradle
org.gradle.jvmargs=-Xmx3g -Dfile.encoding=UTF-8

# Giá trị project property riêng trên máy này
appMode=local-user
~~~

- org.gradle.jvmargs điều chỉnh JVM dùng thực thi Gradle/daemon theo cơ chế Gradle, **không** tự tăng heap của ứng dụng Java chạy bằng task run hay của mọi test worker.
- appMode=local-user sẽ ảnh hưởng đến những build đọc project property appMode qua nguồn cấu hình chuẩn, nếu không có nguồn ưu tiên cao hơn.
- File ở user home không phải một phần của repository. Vì thế nó có thể gây hiện tượng “chạy trên máy tôi khác đồng đội” nếu hai máy dùng giá trị khác nhau.

**Cảnh báo về phạm vi:** User-level gradle.properties có thể ảnh hưởng **nhiều dự án Gradle** của cùng người dùng. Chỉ đặt tại đây các tùy chỉnh thực sự cần áp dụng rộng; tránh thêm key chung chung như version, name, status hoặc các key khó truy nguyên. Đặt config dành riêng một dự án trong user home có thể gây ghi đè bất ngờ ở dự án khác.

### 2.3. Dòng lệnh: một lần chạy Gradle

Tham số **-P** đặt project property cho invocation hiện tại:

~~~bash
./gradlew showConfig -PappMode=staging
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat showConfig -PappMode=staging
~~~

Đây là cách tự nhiên để tạm thử một giá trị. Lần chạy sau không có -P sẽ trở về giá trị từ những nguồn còn lại.

Một biến thể khác là dùng **Java system property có tiền tố đặc biệt**:

~~~bash
./gradlew showConfig -Dorg.gradle.project.appMode=staging
~~~

Khi Gradle thấy tên system property bắt đầu bằng org.gradle.project., nó cung cấp phần tên còn lại thành project property: ở ví dụ trên là appMode.

Một **environment variable** cũng có thể tạo project property nếu tên tuân theo quy ước:

~~~bash
export ORG_GRADLE_PROJECT_appMode=staging
./gradlew showConfig
~~~

Ví dụ tương đương PowerShell:

~~~powershell
$env:ORG_GRADLE_PROJECT_appMode = 'staging'
.\gradlew.bat showConfig
Remove-Item Env:ORG_GRADLE_PROJECT_appMode
~~~

Đây là thiết lập theo **môi trường của tiến trình** và các tiến trình con kế thừa biến đó, khác với thay đổi file. Trong một terminal đang mở, giá trị thường tiếp tục tồn tại cho đến khi bạn gỡ biến, mở terminal mới hoặc hệ thống thay đổi môi trường. Vì vậy "theo một lần chạy" đúng rõ nhất cho **-P/-D CLI**, còn environment variable tồn tại theo phạm vi môi trường mà bạn cấp.

## 3. Bốn loại thuộc tính phải phân biệt

Các cơ chế đều có thể chứa chữ property, nhưng không cùng nơi tiêu thụ:

| Loại | Cách đặt ví dụ | Cách dùng điển hình | Có tự đi vào JVM ứng dụng? |
|---|---|---|---|
| **Gradle property** | org.gradle.caching=true trong gradle.properties | Điều khiển hành vi Gradle | Không |
| **Project property** | appMode=dev trong gradle.properties hoặc -PappMode=dev | Build script/plugin dùng providers.gradleProperty('appMode') | Không |
| **System property của Gradle JVM** | -Ddemo.trace=true hoặc systemProp.demo.trace=true | Build process dùng providers.systemProperty('demo.trace') | Không tự động |
| **Environment variable** | ORG_GRADLE_PROJECT_appMode=dev | Được Gradle chuyển thành project property theo tiền tố; biến môi trường khác có thể được build logic đọc | Không tự động |

**Nhớ hai tiền tố quan trọng:**

- **org.gradle.project.KEY** ở Java system property chuyển thành **project property KEY**. Ví dụ -Dorg.gradle.project.appMode=production.
- **systemProp.KEY** trong gradle.properties tạo **Java system property KEY cho JVM chạy Gradle**, ví dụ systemProp.http.proxyHost=proxy.example.org. Trong multi-project build, chỉ root gradle.properties được xét cho systemProp.* theo quy tắc được Gradle công bố; đừng đặt cùng key rải rác ở subproject rồi chờ tự hợp nhất.

Ví dụ các lệnh sau **không tương đương**:

~~~bash
./gradlew showConfig -PappMode=cli
./gradlew showConfig -DappMode=cli
./gradlew showConfig -Dorg.gradle.project.appMode=cli
~~~

- Lệnh 1 tạo project property appMode.
- Lệnh 2 tạo JVM system property appMode; providers.gradleProperty('appMode') không mặc nhiên nhận giá trị ấy.
- Lệnh 3 tạo system property có tiền tố được Gradle hiểu là project property appMode.

**Lưu ý khác:** JAVA_HOME chỉ một JDK ban đầu cho Gradle launcher/daemon theo điều kiện môi trường; org.gradle.java.home hoặc daemon JVM criteria có thể quyết định JVM chạy build; Java toolchain chỉ JDK cho những task compile/test/run tương ứng. Đây là các cơ chế riêng, không nên coi appMode, org.gradle.java.home, JAVA_HOME và java.toolchain là cùng một thứ.

## 4. Thứ tự ưu tiên khi nhiều nguồn cùng đặt một project property

Đây là phần quan trọng nhất của bài. Với **Provider API providers.gradleProperty('appMode')**, các nguồn được xét theo thứ tự ưu tiên **cao xuống thấp**:

| Độ ưu tiên | Nguồn | Ví dụ |
|---|---|---|
| 1 — Cao nhất | CLI project property -P | -PappMode=cli |
| 2 | JVM system property có tiền tố org.gradle.project. | -Dorg.gradle.project.appMode=system |
| 3 | Environment variable ORG_GRADLE_PROJECT_ | ORG_GRADLE_PROJECT_appMode=environment |
| 4 | GRADLE_USER_HOME/gradle.properties | appMode=user |
| 5 | Build root/gradle.properties | appMode=project |
| 6 — Thấp nhất | Gradle installation/gradle.properties (nếu có) | appMode=installation |

**Ví dụ:** Một build có root/gradle.properties chứa appMode=project, user home chứa appMode=user, môi trường có ORG_GRADLE_PROJECT_appMode=environment và lệnh có -PappMode=cli. Theo thứ tự này, Provider trả về **cli**. Nếu bỏ -P, sẽ còn **environment**, miễn không có nguồn system property ưu tiên cao hơn.

Đây là **thứ tự của project properties** thông qua các nguồn Gradle chuẩn; không áp đặt máy móc cho tất cả loại property. Gradle settings như org.gradle.caching có thể có các CLI flags/setting riêng; Java system properties có thứ tự riêng. Cũng không dùng bảng này để dự đoán kết quả một file tùy biến nếu build script tự đọc file đó rồi gán lại giá trị.

### 4.1. Project root và thư mục subproject không nhất thiết cùng quy tắc

Trong multi-project build:

~~~text
multi-build/
├── settings.gradle
├── gradle.properties                 # nguồn chuẩn ở build root
├── build.gradle
└── service/
    ├── build.gradle
    └── gradle.properties             # không là nguồn build-level cho Provider API
~~~

providers.gradleProperty(...) **không tự nạp** gradle.properties trong thư mục service như một nguồn build-level. Ngược lại, một số API truy xuất thuộc tính động trên Project như findProperty/property có thể xem thêm project-specific properties/extra properties với thứ tự và phạm vi khác.

Để cấu hình **dùng chung cho toàn build** và tránh nhầm, nên đặt project property ở **build root** hoặc nguồn người dùng/CLI chuẩn, sau đó đọc bằng providers.gradleProperty trong module cần nó. Nếu muốn dữ liệu riêng cho service, hãy thiết kế cơ chế tường minh, ví dụ một extension trong :service hoặc một file input riêng có loader rõ ràng.

### 4.2. Truy xuất property bằng API nào?

Một số lựa chọn trong Groovy DSL:

~~~groovy
// Provider: lazy, có thể dùng fallback
def modeProvider = providers.gradleProperty('appMode')
    .orElse('development')

// Truy xuất động trên Project: có thể trả null
def possibleMode = findProperty('appMode')

// Yêu cầu property phải có, thiếu sẽ ném lỗi
def requiredMode = property('appMode')

// Kiểm tra project object có property theo API động
def exists = hasProperty('appMode')
~~~

Đoạn trên là **minh họa đặt trong build.gradle**; nó không phải một chương trình Java độc lập. providers.gradleProperty phù hợp khi cần kết nối giá trị vào task input và hạn chế việc đọc sớm. Còn findProperty/property/hasProperty tìm trong mô hình Project động: extra properties, extension, task và cấu hình theo project có thể thay đổi kết quả so với Provider API, nhất là khi build nhiều module.

**Tránh dùng get() ngay để kết hợp string vào mọi task** nếu bạn có thể truyền Provider trực tiếp qua Property<T> của task. Trong plugin hoặc custom task lớn, Gradle input/output model nên là nơi tiêu thụ provider để tăng khả năng cấu hình lazy, incremental và caching.

### 4.3. Kiểm chứng sự ưu tiên bằng ví dụ

Giả sử cùng tồn tại các giá trị:

~~~text
root/gradle.properties:            appMode=project
GRADLE_USER_HOME/gradle.properties: appMode=user
Environment:                      ORG_GRADLE_PROJECT_appMode=environment
Command line:                     -PappMode=cli
~~~

Khi không có system property ưu tiên cao hơn, lệnh có -P đọc **cli**. Khi bỏ -P nhưng giữ environment thì đọc **environment**. Khi bỏ cả -P, system property và environment thì đọc **user**. Nếu xóa cả user-level value thì đọc **project**.

Bạn không cần xóa toàn bộ ~/.gradle hoặc cache để thử thứ tự ưu tiên. Chỉ thêm/xóa key kiểm thử có chủ đích trong tệp cấu hình phù hợp; nếu thay đổi cấu hình riêng của máy, nhớ khôi phục sau thí nghiệm.

## 5. Thực hành đầy đủ: một dự án Gradle + Java 17

Mục đích thực hành: Gradle đọc appMode và appLabel từ phạm vi dự án/người dùng/CLI, hiển thị giá trị khi chạy task, rồi **truyền tường minh** giá trị đó sang một chương trình Java 17.

### 5.1. Cấu trúc file

~~~text
property-scope-lab/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.properties
│       └── gradle-wrapper.jar
└── src/
    └── main/
        └── java/
            └── demo/
                └── Main.java
~~~

Nếu bắt đầu từ thư mục rỗng, chưa có Wrapper, bạn có thể tạo settings.gradle, build.gradle, gradle.properties và Main.java trước, sau đó chạy **gradle wrapper** bằng một bản Gradle đã được cài để sinh các file Wrapper. Những lần tiếp theo, dùng Wrapper đã đưa vào version control. Cần JDK 17 thích hợp và bản Gradle tương thích với môi trường; nếu toolchain Java 17 chưa sẵn có, Gradle có thể báo lỗi thay vì tự có JDK.

**settings.gradle**

~~~groovy
rootProject.name = 'property-scope-lab'
~~~

**gradle.properties ở root**

~~~properties
org.gradle.caching=true
appMode=from-project
appLabel=Hello Project
~~~

**build.gradle — Groovy DSL**

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
    mainClass = 'demo.Main'
}

// Build-level project properties: các nguồn theo thứ tự ưu tiên Gradle.
def modeProvider = providers.gradleProperty('appMode')
    .orElse('default-mode')
def labelProvider = providers.gradleProperty('appLabel')
    .orElse('Hello Default')

// Task này cho phép nhìn chính xác giá trị Gradle đã resolve.
// inputs.property làm rõ các giá trị ảnh hưởng tới task.
tasks.register('showConfig') {
    inputs.property('appMode', modeProvider)
    inputs.property('appLabel', labelProvider)

    doLast {
        println 'appMode=' + modeProvider.get()
        println 'appLabel=' + labelProvider.get()
    }
}

// Plugin application tạo task run.
// Đây là bước nối cấu hình Gradle vào JVM chạy Java main.
tasks.named('run', JavaExec) {
    systemProperty 'demo.mode', modeProvider.get()
    systemProperty 'demo.label', labelProvider.get()
}
~~~

**src/main/java/demo/Main.java**

~~~java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String mode = System.getProperty("demo.mode", "unset");
        String label = System.getProperty("demo.label", "unset");
        System.out.println("mode=" + mode);
        System.out.println("label=" + label);
    }
}
~~~

Java main dùng System.getProperty(...), vì trong build.gradle bạn đã chủ động cấu hình **systemProperty trên task run**. appMode và appLabel ban đầu là project properties trong build; chỉ đến lúc được chuyển sang demo.mode và demo.label thì JVM ứng dụng mới nhận được hai giá trị.

**Điều kiện để đối chiếu stdout:** Ví dụ kết quả bên dưới giả định không có appMode/appLabel trùng tên ở Gradle User Home, biến môi trường hay tham số override, trừ khi ví dụ chỉ rõ.

### 5.2. Chạy mặc định

Linux/macOS:

~~~bash
./gradlew -q showConfig
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q showConfig
.\gradlew.bat -q run
~~~

Dòng do task showConfig in ra:

~~~text
appMode=from-project
appLabel=Hello Project
~~~

Dòng do chương trình Java in ra khi run:

~~~text
mode=from-project
label=Hello Project
~~~

Gradle có thể in thêm log của nó tùy phiên bản và mức log; hai khối stdout trên chỉ biểu diễn các dòng trong action và Java main. Chương trình Java 17 không cần thư viện bên ngoài, chỉ dùng java.lang.System.

### 5.3. Thử ghi đè tại dòng lệnh

Chạy:

~~~bash
./gradlew -q showConfig -PappMode=from-cli
./gradlew -q run -PappMode=from-cli
~~~

Task showConfig in:

~~~text
appMode=from-cli
appLabel=Hello Project
~~~

Java main in:

~~~text
mode=from-cli
label=Hello Project
~~~

Nếu dùng -D có tiền tố đặc biệt, kết quả tương ứng:

~~~bash
./gradlew -q showConfig -Dorg.gradle.project.appMode=from-system
~~~

~~~text
appMode=from-system
appLabel=Hello Project
~~~

Trong trường hợp cả -PappMode=from-cli và -Dorg.gradle.project.appMode=from-system cùng xuất hiện, giá trị **from-cli** thắng. Lý do là thứ tự ưu tiên của **project property**, không phải vì -D không hoạt động.

### 5.4. Thử ghi đè tại cấp người dùng

Trong GRADLE_USER_HOME/gradle.properties của môi trường thử nghiệm, thêm:

~~~properties
appMode=from-user
~~~

Sau đó chạy lại mà không có -P, -Dorg.gradle.project.appMode hay biến môi trường ORG_GRADLE_PROJECT_appMode:

~~~bash
./gradlew -q showConfig
~~~

Kết quả:

~~~text
appMode=from-user
appLabel=Hello Project
~~~

**Giải thích:** Giá trị appMode từ user home thắng root/gradle.properties; appLabel vẫn là giá trị project vì không có nguồn nào ghi đè. Trước khi kết luận Gradle lỗi, hãy kiểm tra đúng **GRADLE_USER_HOME đang được dùng**, bởi nó có thể khác ~/.gradle mặc định.

**Cách kết thúc thí nghiệm:** Xóa đúng dòng appMode=from-user mà bạn vừa thêm vào file user home thử nghiệm, không xóa toàn bộ file hay cấu hình thực tế của người dùng. Không commit thay đổi user home vào repository.

### 5.5. Thử environment variable

Trên Linux/macOS, trong một shell không có nguồn ưu tiên cao hơn:

~~~bash
ORG_GRADLE_PROJECT_appMode=from-environment ./gradlew -q showConfig
~~~

Đầu ra:

~~~text
appMode=from-environment
appLabel=Hello Project
~~~

Trên Windows PowerShell có thể làm tương tự với biến môi trường của phiên hiện tại:

~~~powershell
$env:ORG_GRADLE_PROJECT_appMode = 'from-environment'
.\gradlew.bat -q showConfig
Remove-Item Env:ORG_GRADLE_PROJECT_appMode
~~~

Trong thực tế, environment variable thường hữu ích khi CI cung cấp giá trị mà không phải sửa file; tuy nhiên cần tránh tên khó thao tác trên các hệ điều hành, ví dụ key có dấu chấm trong tên biến môi trường. Nếu dự định dùng ORG_GRADLE_PROJECT_ thì đặt key gọn như appMode thay vì app.mode.

### 5.6. Truyền tường minh giá trị sang JVM ứng dụng

Trong build.gradle, đoạn:

~~~groovy
tasks.named('run', JavaExec) {
    systemProperty 'demo.mode', modeProvider.get()
    systemProperty 'demo.label', labelProvider.get()
}
~~~

có ý nghĩa là **task run** tạo JVM cho ứng dụng với hai Java system properties. Nếu bỏ đoạn này, Main.java vẫn biên dịch nhưng sẽ in:

~~~text
mode=unset
label=unset
~~~

Điều này đúng với mã Java đang dùng vì System.getProperty(key, defaultValue) trả về giá trị mặc định khi key không được cung cấp. Việc đặt appMode trong gradle.properties không tự sửa nội dung class file hay bảo đảm ứng dụng chạy trực tiếp bằng java -cp ... nhận được property.

Nếu muốn ứng dụng đã deploy nhận cấu hình, nên dùng cơ chế runtime phù hợp (environment, JVM -D cho ứng dụng, args hoặc framework config); cần tài liệu hóa đường đi của dữ liệu thay vì giả định build property sẽ tự mang theo vào JAR.

### 5.7. Một lệnh khác: ứng dụng Java chạy trực tiếp

Sau khi chạy task classes:

~~~bash
./gradlew classes
java -cp build/classes/java/main demo.Main
~~~

Nếu không thêm Java system properties vào lệnh java độc lập, stdout là:

~~~text
mode=unset
label=unset
~~~

Muốn cung cấp giá trị lúc chạy Java trực tiếp:

~~~bash
java -Ddemo.mode=production -Ddemo.label=HelloCLI -cp build/classes/java/main demo.Main
~~~

Kết quả:

~~~text
mode=production
label=HelloCLI
~~~

**Sự khác biệt mấu chốt:** -Ddemo.mode=... trước class name là **Java system property của tiến trình Java được gọi trực tiếp**. Còn -Dorg.gradle.project.appMode=... ở lệnh ./gradlew là cơ chế Gradle ánh xạ một system property thành project property trong quá trình build.

## 6. Gradle property: cách chọn cấu hình của chính Gradle

Một số key có tiền tố org.gradle. được Gradle định nghĩa sẵn:

~~~properties
# root/gradle.properties
org.gradle.caching=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx2g -Dfile.encoding=UTF-8
~~~

- org.gradle.caching cấu hình sử dụng build cache khi task đủ điều kiện.
- org.gradle.parallel cho phép Gradle cân nhắc chạy song song công việc theo quy tắc của Gradle; không bảo đảm mọi task đều chạy song song.
- org.gradle.jvmargs cấu hình các tùy chọn JVM cho daemon chạy Gradle. Nó không phải tham số JVM mặc định cho ứng dụng do JavaExec fork ra.

Khi một **Gradle property** được đặt ở nhiều gradle.properties, Gradle ưu tiên file trong GRADLE_USER_HOME, sau đó root build, sau đó Gradle installation. Một số thiết lập có tùy chọn dòng lệnh riêng; ví dụ có thể dùng -Dorg.gradle.caching=true/false để kiểm tra một thuộc tính cụ thể theo quy tắc được Gradle hỗ trợ.

**Không suy diễn** -Porg.gradle.caching=true là cách chuẩn để sửa Gradle setting. -P là project property; cơ chế điều khiển trực tiếp Gradle property và tên flag của Gradle cần được tra trong tài liệu riêng. Tương tự, một setting có tên org.gradle.jvmargs không nên được đọc qua providers.gradleProperty để viết nghiệp vụ ứng dụng: Gradle đã có trách nhiệm tiêu thụ setting đó.

### 6.1. JDK chạy Gradle và Java toolchain

Bốn cơ chế thường bị nhầm:

| Cơ chế | Phạm vi | Ví dụ |
|---|---|---|
| JAVA_HOME | Môi trường quyết định Java launcher ban đầu khi dùng Gradle Wrapper | Đường dẫn JDK cài trên máy |
| org.gradle.java.home | Hướng dẫn Gradle sử dụng Java home cho daemon/build JVM theo quy tắc Gradle | Giá trị đường dẫn địa phương |
| Daemon JVM criteria | Tiêu chí chọn JVM cho daemon khi dự án có cấu hình tương ứng | Quy định JDK/phiên bản dùng cho daemon |
| java.toolchain.languageVersion | Chọn toolchain cho compile/test và những task được plugin hỗ trợ | JavaLanguageVersion.of(17) |

Vì đường dẫn JDK có thể khác theo hệ điều hành, **tránh commit org.gradle.java.home tuyệt đối trỏ tới máy một cá nhân** trong file dự án chung. Thay vào đó, quản trị JDK qua công cụ cài đặt, toolchain và CI. Khi build sai JDK, xem ./gradlew --version, JAVA_HOME, thiết lập daemon và toolchain; đừng chỉ đổi -PappMode.

## 7. Cấu hình ở CLI khác với sửa file ở những điểm nào?

| Mục tiêu | Nơi nên đặt | Lý do |
|---|---|---|
| Giá trị mặc định áp dụng cho mọi thành viên | Root gradle.properties | Có version control, nhất quán khi checkout |
| Thông số riêng của một người/máy | GRADLE_USER_HOME/gradle.properties | Không đẩy thiết lập máy cá nhân vào Git |
| Giá trị kiểm thử tạm thời | -Pkey=value | Chỉ áp dụng cho invocation hiện tại, dễ kiểm chứng |
| Dữ liệu do CI cấp khi chạy | ORG_GRADLE_PROJECT_key hoặc cơ chế CI tương ứng | Không cần chỉnh file build/commit |
| Java system property của Gradle | -Dkey=value hoặc systemProp.key=value theo quy tắc Gradle | Ảnh hưởng JVM chạy Gradle, không tự tác động mọi JVM khác |
| Cấu hình JVM khi chạy ứng dụng | JavaExec.systemProperty, applicationDefaultJvmArgs hoặc lệnh java -D | Đặt đúng vào JVM tiêu thụ |
| Cấu hình ứng dụng runtime nhiều môi trường | Runtime config của ứng dụng/framework | Không phụ thuộc lần build ra JAR |

Đừng chuyển mọi thiết lập sang -P chỉ để “cấp cao nhất”: khi một giá trị chung phải truyền tay trong từng lệnh, người khác dễ quên hoặc chạy CI không nhất quán. Dùng root gradle.properties cho mặc định hợp lý, cho phép CLI ghi đè **khi có nhu cầu rõ ràng**.

## 8. Lưu secret và cấu hình CI một cách an toàn

Một số dự án cần token để lấy artifact từ repository riêng hoặc ký bản phát hành. Secret có thể được cung cấp từ Gradle user home hoặc biến môi trường CI, nhưng **bản thân tên tệp gradle.properties không tự mã hóa hay bảo mật giá trị**.

Nguyên tắc thực hành:

1. **Không commit secret thật**, dù nó nằm trong root gradle.properties, local.properties hay tệp tự định nghĩa.
2. **Ưu tiên secret manager của CI** để cấp giá trị khi chạy; hạn chế in property ra log, task report hoặc build scan.
3. **Hạn chế truyền secret qua -P trên dòng lệnh**, vì lịch sử shell, process list và log CI có thể ghi lại câu lệnh. Khi phù hợp, dùng ORG_GRADLE_PROJECT_* từ môi trường của tiến trình, không ghi thành giá trị trong script đã commit.
4. **Giới hạn phạm vi:** Nếu chỉ một task/plugin cần secret, đừng để nó nằm trong chuỗi log hoặc ghép vô điều kiện vào tên artifact.
5. **Kiểm tra tên biến môi trường** và quy tắc precedence. Nếu vừa có ORG_GRADLE_PROJECT_token từ CI vừa có -Ptoken=..., -P sẽ thắng theo mô hình project property, có thể khiến token được chọn khác điều bạn dự kiến.
6. **Không biến mọi secret thành một project property** nếu plugin đã có cơ chế credential Provider riêng phù hợp. Dùng API an toàn của plugin để tránh vô tình lộ giá trị.

Ví dụ code truy xuất Provider **không in giá trị**:

~~~groovy
def repositoryToken = providers.gradleProperty('repoToken')

// Chỉ truyền Provider vào cấu hình/plugin hỗ trợ,
// tránh println repositoryToken.get() khi token có thể là secret.
~~~

Đây là đoạn minh họa một phần, **không phải build script độc lập**. Nếu build thực sự cần token, logic cần kiểm tra thiếu giá trị và cấu hình authentication/credentials đúng theo repository/plugin sử dụng.

## 9. Các lỗi dễ gặp và cách chẩn đoán

### 9.1. "Đã sửa root gradle.properties nhưng giá trị vẫn là của máy tôi"

**Nguyên nhân:** GRADLE_USER_HOME/gradle.properties chứa cùng key và ưu tiên cao hơn root file, hoặc environment/CLI đang ghi đè.

**Cách kiểm tra:** Tìm đúng key trong các nguồn sau theo thứ tự: -P, -Dorg.gradle.project.*, ORG_GRADLE_PROJECT_*, user home, root, installation. Với key không nhạy cảm, dùng một task nhỏ in giá trị để đối chiếu. Không vội xóa toàn bộ ~/.gradle.

### 9.2. "Máy A đọc được property, máy B báo thiếu"

**Nguyên nhân:** Giá trị chỉ tồn tại trong user home của máy A hoặc trong shell riêng; root không có mặc định.

**Cách xử lý:** Nếu đó là thiết lập chung, thêm một default không nhạy cảm vào root gradle.properties hoặc dùng orElse trong Provider. Nếu là giá trị bắt buộc khác theo máy/CI, tài liệu hóa cách cung cấp và báo lỗi rõ ràng khi thiếu.

### 9.3. "-DappMode=staging không đổi providers.gradleProperty('appMode')"

**Nguyên nhân:** -DappMode là một Java system property, không phải project property được ánh xạ tự động.

**Cách xử lý:** Dùng -PappMode=staging, hoặc -Dorg.gradle.project.appMode=staging, hoặc đọc nó bằng providers.systemProperty('appMode') nếu thực sự muốn dùng JVM system property.

### 9.4. "Thêm appMode vào gradle.properties nhưng Java main vẫn là unset"

**Nguyên nhân:** Project property trong Gradle và Java system property của ứng dụng là hai phạm vi khác nhau.

**Cách xử lý:** Cấu hình task run/test truyền systemProperty vào JVM; hoặc cho ứng dụng đọc runtime config khi nó thực thi. Dùng đúng ví dụ trong mục 5 để quan sát sự khác biệt.

### 9.5. "Property trong service/gradle.properties không được Provider API đọc"

**Nguyên nhân:** providers.gradleProperty lấy nguồn **build-level**, không bao gồm gradle.properties ở subproject directories. Một số API Project động có phạm vi khác nên kết quả có thể không giống nhau.

**Cách xử lý:** Đặt property tại root hoặc nguồn build-level chuẩn, hoặc thiết kế extension/file riêng cho subproject và nêu rõ API sử dụng.

### 9.6. "Chạy -Pfoo nhưng property trả về ở nơi khác vẫn khác"

**Nguyên nhân:** Code khác đọc từ findProperty, extra properties, systemProperty hoặc một file do plugin tự nạp. Một extra property được đặt tường minh có thể chiếm ưu tiên trong cách tra cứu trên đối tượng Project dù providers.gradleProperty vẫn đọc build-level property.

**Cách xử lý:** Xác định **API đã đọc giá trị** và nguồn nó hỗ trợ. Tránh cùng tên key cho nhiều cơ chế độc lập; dùng Provider API nhất quán khi đây là một project property chuẩn.

### 9.7. "Build CI báo hết bộ nhớ dù đã đặt org.gradle.jvmargs trong project"

**Nguyên nhân có thể:** User-level value hoặc CLI đã ghi đè; lỗi nằm ở JVM khác (test worker, JavaExec, Kotlin daemon); hoặc worker count/JVM memory cần được quản lý riêng.

**Cách xử lý:** Xác định tiến trình báo lỗi và cấu hình chính tiến trình ấy. org.gradle.jvmargs không bảo đảm memory của mọi JVM phụ thuộc; kiểm tra thuộc tính Gradle/JDK của môi trường thực tế thay vì tăng mọi heap ngẫu nhiên.

### 9.8. "Ứng dụng chạy production khác sau khi dùng -PappMode=production để build"

**Nguyên nhân:** Giá trị build-time không tự trở thành cấu hình runtime của ứng dụng sau đóng gói. Nếu build script chỉ truyền property cho task run, Java chạy từ JAR trong môi trường khác sẽ không tự có giá trị.

**Cách xử lý:** Xác định cần nhúng giá trị khi build hay cấp ở runtime. Với secrets, hostname, database credentials và môi trường production, thường nên cấp qua cơ chế runtime/secret manager, tránh nhúng vào artifact.

### 9.9. "Không biết GRADLE_USER_HOME thực tế nằm đâu"

**Nguyên nhân:** Hệ điều hành, IDE, terminal hoặc CI thiết lập Gradle User Home khác nhau; một số tiến trình chạy dưới tài khoản khác.

**Cách xử lý:** Kiểm tra môi trường Gradle thực tế và tham số cấu hình User Home của tiến trình đang chạy. Trên máy cá nhân thường bắt đầu từ ~/.gradle; trong CI thường có path cache riêng. Không suy đoán user home từ tên repository.

## 10. Thực hành tình huống và chọn đúng nguồn

### Tình huống A: Cả nhóm đều bật build cache

**Nên dùng:** root gradle.properties chứa org.gradle.caching=true và commit vào Git. Từng máy vẫn có thể ghi đè có chủ đích bằng cơ chế ưu tiên của Gradle; nếu build cache gây vấn đề hãy chẩn đoán task input/output trước.

### Tình huống B: Một người cần tăng memory Gradle daemon

**Nên dùng:** GRADLE_USER_HOME/gradle.properties chứa org.gradle.jvmargs phù hợp máy đó. Không commit đường dẫn hoặc mức heap chỉ hợp cho một máy vào file dự án chung nếu không được nhóm thống nhất.

### Tình huống C: CI cần build cho staging rồi production

**Nên dùng:** Một project property như appMode với mặc định development ở root, CI truyền -PappMode=staging hay ORG_GRADLE_PROJECT_appMode=production. Phải xác định build script/plugin **thực sự dùng** property đó ở đâu.

### Tình huống D: Gradle build đọc artifact từ repository private

**Nên dùng:** Secret manager của CI hoặc nguồn riêng của người dùng, nối vào credentials thông qua API hỗ trợ Provider. Không commit token và không in ra console khi debug.

### Tình huống E: Muốn mọi task compile dùng Java 17

**Nên dùng:** Java toolchain trong java { toolchain { ... } } của project/plugin phù hợp. Java version cho compile không nên được biểu diễn chỉ bằng -PappMode. Cần phân biệt JDK chạy Gradle, toolchain cho compile/test và JVM chạy ứng dụng.

### Tình huống F: Một subproject có tham số riêng

**Nên dùng:** Build root property có tên rõ ràng như servicePort hoặc extension cấu hình trong project :service. Chỉ dùng service/gradle.properties nếu chủ động chọn API nhận biết nguồn đó; đừng kỳ vọng Provider API tự quét mọi subproject.

## 11. Tóm tắt lựa chọn và bài tập kiểm tra

| Câu hỏi | Câu trả lời ngắn |
|---|---|
| Giá trị mặc định dùng chung ở đâu? | Root gradle.properties, commit nếu không nhạy cảm |
| Giá trị riêng của người/máy ở đâu? | GRADLE_USER_HOME/gradle.properties hoặc nguồn local được quản lý |
| Thay tạm một project property bằng gì? | -Pkey=value |
| Chuyển system property thành project property bằng cách nào? | -Dorg.gradle.project.key=value |
| Đặt project property từ CI environment? | ORG_GRADLE_PROJECT_key=value |
| Đọc project property chuẩn theo API nào? | providers.gradleProperty('key') |
| Nguồn nào thắng: -P hay user-level file? | -P |
| Nguồn nào thắng: env ORG_GRADLE_PROJECT_ hay user-level file? | Environment |
| Một project property tự đi vào Java main? | Không, phải có kết nối tường minh hoặc runtime config |
| Một file service/gradle.properties có tự thuộc nguồn build-level Provider API? | Không |
| Đặt Gradle daemon heap ở đâu? | org.gradle.jvmargs phù hợp cơ chế Gradle |
| Thay JDK Java compile bằng gì? | Java toolchain |

**Bài tập 1.** root/gradle.properties chứa appMode=root, user home chứa appMode=user. Chạy ./gradlew showConfig không có CLI/env/system override. providers.gradleProperty('appMode') trả về gì?

**Bài tập 2.** Giữ hai file ở bài 1, thêm ORG_GRADLE_PROJECT_appMode=env và -PappMode=cli. Giá trị nào thắng? Bỏ -P thì còn gì?

**Bài tập 3.** Chạy ./gradlew showConfig -DappMode=system. Build script chỉ đọc providers.gradleProperty('appMode'). Có chắc sẽ đọc system không? Cần đổi cách đặt hoặc cách đọc như thế nào?

**Bài tập 4.** Có file root/gradle.properties chứa appMode=production. Bạn chạy java -cp build/classes/java/main demo.Main mà không truyền -Ddemo.mode. Main sẽ thấy gì và vì sao?

**Bài tập 5.** Một developer đặt org.gradle.jvmargs=-Xmx5g trong user home, nhưng một server chạy test bằng một JVM riêng vẫn hết heap. Vì sao tăng heap Gradle không nhất thiết đủ?

**Bài tập 6.** Vì sao không nên commit token vào root gradle.properties, và cách cấp token vào CI hợp lý hơn là gì?

**Đáp án gợi ý:**

1. user, vì user home ưu tiên cao hơn build root.
2. cli thắng tất cả; bỏ -P thì env thắng (nếu không có system property ưu tiên cao hơn).
3. Không. Dùng -PappMode=system hoặc -Dorg.gradle.project.appMode=system; nếu muốn đọc -DappMode, dùng providers.systemProperty('appMode').
4. mode=unset nếu không có runtime JVM property demo.mode; project property chỉ nằm trong build logic cho đến khi được truyền tường minh.
5. Vì org.gradle.jvmargs cấu hình Gradle daemon, còn task Test hoặc JavaExec có thể dùng JVM riêng với thiết lập memory khác.
6. Token trong repository/history/log dễ bị lộ. CI nên dùng secret manager và cấp vào tiến trình theo cơ chế được plugin hỗ trợ, tránh in giá trị.

## Tài liệu chính thức

- [Gradle User Manual — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): gradle.properties, thứ tự ưu tiên, Gradle/project/system properties và environment variables.
- [Gradle API — ProviderFactory.gradleProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ProviderFactory.html): thứ tự các nguồn build-level và giới hạn với subproject gradle.properties.
- [Gradle User Manual — Gradle Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): dùng Provider/Property để truy xuất lazy và nối input của task.
- [Gradle User Manual — Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): đặt các Gradle flags dùng chung trong root gradle.properties.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): các cú pháp -P, -D và tùy chọn chạy task.
- [Gradle User Manual — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): phân biệt JDK compile/test với JVM chạy Gradle.

**Ghi nhớ:** Dùng **root/gradle.properties** cho mặc định chung; **GRADLE_USER_HOME/gradle.properties** cho cấu hình riêng của người dùng; **-P** cho một lần chạy, cùng với **-Dorg.gradle.project.*** và **ORG_GRADLE_PROJECT_*** khi cần cung cấp project property qua các kênh tương ứng. Đọc giá trị bằng đúng API, hiểu thứ tự ưu tiên và chủ động nối vào task/JVM tiêu thụ.