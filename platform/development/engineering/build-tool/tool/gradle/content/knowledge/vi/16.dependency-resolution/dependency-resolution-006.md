# Resolution strategy, force và phạm vi tác động

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Phân giải dependency

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **dependency declaration** (yêu cầu một dependency) với **dependency resolution** (Gradle chọn component, version, variant và artifact thực tế).
2. Hiểu **ResolutionStrategy** thuộc về từng **Configuration**, không phải một thiết lập tự động áp dụng cho mọi project hoặc mọi classpath.
3. Giải thích **resolutionStrategy.force(...)** ép version của một module khi graph có yêu cầu đến module đó, kể cả khi yêu cầu nằm ở dependency bắc cầu.
4. Phân tích phạm vi và hệ quả khi đặt rule trên runtimeClasspath, compileClasspath, testRuntimeClasspath, configurations.configureEach và từng subproject.
5. So sánh force với **eachDependency/useVersion**, **dependency constraints** (strictly/prefer), **failOnVersionConflict**, **component selection**, **dependency substitution**, **locking** và **verification**.
6. Chạy dự án **Gradle Groovy DSL + Java 17** để thấy cùng một module có thể được chọn phiên bản khác ở compileClasspath và runtimeClasspath.
7. Dùng **dependencies** và **dependencyInsight** để xác nhận phiên bản được yêu cầu, được chọn, lý do như **Forced**; không dự đoán kết quả chỉ từ một dòng trong build.gradle.
8. Nhận diện trường hợp force gây rủi ro về **binary compatibility, security, reproducibility** và library publication.

**Ý chính:** Force là **quy tắc phân giải phiên bản trong một configuration**, không phải cách thêm dependency. Một rule ép version có thể tác động đến direct lẫn transitive requests trong graph được resolve nhưng không tự thay đổi project khác, classpath khác, các phiên bản thực sự có sẵn trong repository hay binary compatibility của thư viện.

## 1. Từ khai báo dependency đến kết quả resolution

Khi viết:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.12.0'
}
~~~

bạn chỉ yêu cầu Commons Lang phiên bản 3.12.0. Nếu một dependency khác yêu cầu Commons Lang 3.14.0, Gradle phải xác định cuối cùng compiler/JVM sẽ nhìn thấy version nào. Đó là **dependency resolution**.

~~~text
implementation 'org.apache.commons:commons-lang3:3.12.0'
    |
    +-- Một dependency khác yêu cầu 3.14.0
    |
    v
Resolvable configuration: compileClasspath / runtimeClasspath
    |
    +-- Đọc direct + transitive requests
    +-- Áp dụng version constraints, rich versions và resolution rules
    +-- Xử lý conflicts và chọn component/variant
    +-- Xác định artifact/file thực tế
    |
    v
Classpath cuối cùng của Java compiler hoặc JVM
~~~

Với hai yêu cầu phiên bản 3.12.0 và 3.14.0 đơn giản, không có rule/constraint khác, Gradle bình thường sẽ chọn **3.14.0**. Nhưng đừng tuyệt đối hóa quy tắc “lúc nào cũng chọn version lớn nhất”: strict constraints, rejects, platforms, variants, capabilities hoặc rules có thể làm kết quả khác đi, kể cả thất bại.

### 1.1. Thuật ngữ phải phân biệt

| Thuật ngữ | Ý nghĩa |
|---|---|
| **Requested version** | Phiên bản được một nhánh dependency graph yêu cầu |
| **Selected version** | Phiên bản cuối Gradle chọn cho một module trong **graph cụ thể** |
| **Direct dependency** | Yêu cầu khai báo trực tiếp trong build |
| **Transitive dependency** | Yêu cầu xuất phát từ metadata của dependency khác |
| **Version conflict** | Có các yêu cầu version cạnh tranh cho một module |
| **Resolution rule** | Rule thay đổi/can thiệp quá trình chọn dependency, chẳng hạn force |
| **Variant-aware resolution** | Chọn đúng variant dựa trên attributes của consumer; không chỉ chọn version |
| **Artifact resolution** | Lấy JAR/file tương ứng với component/variant được chọn |

Dependency resolution **không phải** hành động tải lại mọi file JAR. Resolution xây graph và chọn component/variant; artifact sau đó có thể được lấy từ cache hoặc repository. Force chọn version không tự tạo artifact chưa được publish.

## 2. ResolutionStrategy được đặt ở đâu?

Mỗi Gradle project có **ConfigurationContainer** riêng. Một Configuration có **ResolutionStrategy** để chỉ đạo việc resolve graph của chính configuration đó.

Ví dụ trong build.gradle của Java application:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Đọc chính xác:

- configurations.named('runtimeClasspath') chọn **runtimeClasspath của project đang cấu hình**.
- resolutionStrategy.force(...) ép version module khớp group/name trong **graph runtimeClasspath được resolve**.
- Nếu không có request đến Commons Lang trong graph, force **không tự thêm Commons Lang**.
- Rule này không tự thay đổi compileClasspath, testRuntimeClasspath, compileClasspath của :core hoặc dependency graph của Gradle plugins.

### 2.1. Ba vai trò configuration

| Vai trò | Ví dụ | Chức năng |
|---|---|---|
| **Declarable/dependency scope** | implementation, runtimeOnly, testImplementation | Bucket dùng khai báo dependency |
| **Resolvable** | compileClasspath, runtimeClasspath, testRuntimeClasspath | Dùng giải quyết graph, lấy artifacts cho task |
| **Consumable** | apiElements, runtimeElements từ java-library | Variant xuất cho project/consumer khác |

**Quan trọng:** Việc một configuration extendsFrom(implementation) để nhận dependencies **không đồng nghĩa ResolutionStrategy của implementation sẽ tự chuyển sang các configuration resolve**. Nếu muốn ảnh hưởng compile/runtime classpaths, nhắm trực tiếp các resolvable configurations hoặc định nghĩa một chính sách bao phủ chúng.

### 2.2. Scope chính xác: một configuration

~~~groovy
plugins {
    id 'application'
}

configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Khi :app:run resolve runtimeClasspath, rule có tác dụng. Nhưng :app:compileJava dùng compileClasspath, nên **không tự nhận** force này. Nếu code compile với API mới của Commons Lang nhưng app chạy phiên bản cũ hơn, có thể gặp lỗi ABI ở runtime.

### 2.3. Scope rộng: mọi configuration của một project

~~~groovy
configurations.configureEach {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Rule được gắn cho các configurations trong **project chứa đoạn build.gradle**. Chúng có thể gồm compileClasspath, runtimeClasspath, testRuntimeClasspath, annotationProcessor và configurations khác do plugin tạo. Nó **không có nghĩa tất cả graph bị resolve ngay**, cũng **không tự áp dụng cho subprojects**.

configureEach là cách cấu hình lazy phù hợp hơn so với eager configurations.all { ... } trong nhiều trường hợp. Nhưng **lazy không làm scope hẹp đi**: một rule rộng vẫn có thể ảnh hưởng các công cụ code generation và tests nếu những graphs đó chứa cùng module.

### 2.4. Scope nhiều project

Giả sử:

~~~text
root
├── :core
├── :app
└── :tool
~~~

Nếu **app/build.gradle** có:

~~~groovy
configurations.configureEach {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

chỉ configurations **của app** được cấu hình. Khi app resolve một graph chứa transitive Commons Lang từ core, rule **trong graph app** có thể ép transitive version. Nhưng khi Gradle biên dịch core với :core:compileClasspath, force của app **không điều khiển graph compile độc lập của core**.

Tương tự, đoạn configurations.configureEach trong **root build.gradle** chỉ cấu hình root configurations, không tự cấu hình :app hay :core. Khi nhiều project cần cùng chính sách, nên đóng gói vào **convention plugin** và áp dụng có chủ đích cho từng project.

Không nên dùng allprojects/subprojects để ép phiên bản cho toàn build theo thói quen. Cách này làm các module phụ thuộc vào cấu hình chéo, giảm tính độc lập và có thể gây vấn đề với isolated projects/configuration cache.

### 2.5. Test, annotation processor và plugins

Java plugin tạo nhiều resolvable configurations, ví dụ:

~~~text
compileClasspath
runtimeClasspath
testCompileClasspath
testRuntimeClasspath
annotationProcessor
~~~

Runtime force của application không tự có trong testRuntimeClasspath hoặc annotationProcessor. Muốn kiểm tra test, hãy xem **đúng testRuntimeClasspath**. Ngoài ra, Gradle plugins được resolve thông qua plugin management/buildscript classpath riêng; force tại runtimeClasspath của ứng dụng **không** sửa lỗi tải Gradle plugin hay version của Gradle Wrapper.

## 3. force(...) làm gì và không làm gì?

### 3.1. Cú pháp và cách áp dụng

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Version được ép theo tọa độ group:name:version. API cũng nhận nhiều notations:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0',
        'commons-io:commons-io:2.15.1'
    )
}
~~~

Đây là ví dụ hai rules; **nó không làm thư viện thứ hai xuất hiện** nếu runtime graph không yêu cầu commons-io.

Force có thể ép phiên bản **thấp hơn** phiên bản mà conflict resolution bình thường chọn, ví dụ graph yêu cầu Commons Lang 3.12.0 và 3.14.0 nhưng runtime bị ép 3.12.0. Đây là quyết định cần được kiểm thử kỹ nếu code/thư viện khác từng biên dịch với bản mới.

### 3.2. Những giới hạn quan trọng

Force **không**:
1. Khai báo một dependency mới.
2. Thêm transitive dependency vốn không tồn tại trong metadata/graph.
3. Tạo module hoặc version không có trong Maven/Ivy repository.
4. Sửa method signatures, class bytecode hoặc bảo đảm binary compatibility.
5. Tự đồng bộ compileClasspath và runtimeClasspath nếu chỉ đặt trên một trong hai.
6. Áp dụng ngầm cho mọi subproject, included build, plugin classpath hoặc test configuration.
7. Tự được publish như dependency constraint để consumer bên ngoài nhận chính sách.
8. Bật dependency locking hoặc dependency verification.
9. Xử lý trùng class giữa hai file dependencies không có module identity.
10. Thay đổi version của Gradle Wrapper, JDK hoặc toolchain.

### 3.3. Force và forcedModules

Gradle phân biệt thao tác **thêm** và **thay danh sách** modules bị ép:

~~~groovy
configurations.named('runtimeClasspath') {
    // Thêm một module vào danh sách forced modules.
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Dạng thay toàn bộ forced modules:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.forcedModules = [
        'org.apache.commons:commons-lang3:3.12.0'
    ]
}
~~~

Hai đoạn là **lựa chọn thay thế**, không cần đặt đồng thời. force(...) có thể được gọi nhiều lần để thêm modules; gán forcedModules thay danh sách đang có, do đó có thể loại các force khác từng được plugin đăng ký. Chỉ dùng khi hiểu rõ ownership của resolution policy.

### 3.4. Strict version không phải lúc nào thắng force

Tài liệu Gradle hiện đại nêu rõ resolutionStrategy.force(...) **có thể override một dependency constraint strictly** trong graph, kể cả chọn version ngoài range mà strictly cho phép. A dependency resolve rule dạng eachDependency/useVersion cũng có thể override strictly.

Vì vậy:
- **strictly** biểu thị yêu cầu version như một **rich version constraint** trong dependency graph.
- **force** là một lựa chọn ép **ở mức resolution strategy của consumer configuration**.
- Đừng khẳng định một dependency đã strictly thì tuyệt đối không thể bị consumer thay version bằng resolution strategy.
- Việc Gradle chọn xong phiên bản ép không bảo đảm mã vẫn chạy được.

Trong build logic dài hạn, ưu tiên constraints/strictly để mô tả version intent và khả năng publish metadata; dành force cho trường hợp cần override có lý do.

## 4. So sánh force với các cơ chế khác

| Công cụ | Mục đích | Lưu ý quan trọng |
|---|---|---|
| **force('g:m:v')** | Ép module g:m chọn version v | Local resolution rule của configuration |
| **eachDependency { useVersion(...) }** | Biến đổi version của requests khớp điều kiện | Có thể xử lý cả transitive requests |
| **dependency constraints** | Biểu đạt yêu cầu/ràng buộc version trong graph | Có thể publish qua Gradle Module Metadata |
| **strictly('v')** | Chỉ chấp nhận một version/range phù hợp trong graph | Có thể bị local resolution strategy override |
| **prefer('v')** | Mong muốn version nhưng không bắt buộc | Yêu cầu/constraint mạnh hơn có thể thắng |
| **reject('v')** | Loại version không phù hợp | Có thể làm resolution fail khi không có candidate |
| **failOnVersionConflict()** | Báo lỗi khi graph có version conflict | Phát hiện, không chọn giúp version |
| **componentSelection** | Reject candidates dựa trên quy tắc | Ví dụ chặn phiên bản bị lỗi |
| **dependencySubstitution** | Thay component/module/project request | Có thể thay identity, không chỉ version |
| **preferProjectModules()** | Ưu tiên project components trong trường hợp tranh chấp | Hữu ích với một số multi/composite builds |
| **dependency locking** | Ghi những versions đã resolve để tái lập | Lock state cần quản lý và cập nhật |
| **dependency verification** | Xác minh checksum/signature metadata/artifacts | Không thay việc chọn version |
| **enforcedPlatform** | Ép constraints mạnh từ platform | Có ảnh hưởng metadata/consumer, cần thận trọng |

### 4.1. eachDependency/useVersion

Ví dụ đặt rule có điều kiện trên một configuration:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.eachDependency { details ->
        if (details.requested.group == 'org.apache.commons' &&
            details.requested.name == 'commons-lang3') {
            details.useVersion('3.12.0')
            details.because('Tái hiện môi trường đã kiểm thử')
        }
    }
}
~~~

- Rule xem từng dependency request được resolve, kể cả transitive.
- details.requested chứa thông tin group/name/version yêu cầu.
- useVersion thay **version của request** theo điều kiện; version cuối vẫn chịu ảnh hưởng tổng graph và rules liên quan.
- because cung cấp lý do giúp dependencyInsight dễ hiểu.

**Khác với force:** eachDependency có điều kiện chi tiết trên requests; force khai báo module/version cần ép trong configuration. Khi nhiều force/eachDependency/substitutions cùng áp dụng, đừng suy đoán thứ tự thắng-thua chỉ bằng vị trí dòng code. Kiểm chứng resolved graph và giản lược các rules mâu thuẫn.

### 4.2. Dependency constraint với strictly

Một cách khác để đặt version intent:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.12.0'

    constraints {
        implementation('org.apache.commons:commons-lang3') {
            version {
                strictly('3.12.0')
            }
            because 'Đã xác minh tương thích với phiên bản này'
        }
    }
}
~~~

Đây là **ví dụ thay thế** force, không chèn nó cùng mọi rule vào bài lab. Constraint không tự thêm module nếu không có yêu cầu đến module ấy; nó tác động cách chọn phiên bản khi module có trong graph. Trong thư viện publish, constraints có thể được ghi vào Gradle Module Metadata.

Trong một graph có strict constraints không tương thích, resolution có thể thất bại. Force có thể override chúng nhưng không nên dùng để che điều kiện compatibility mà thư viện đã công bố.

### 4.3. failOnVersionConflict

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.failOnVersionConflict()
}
~~~

Khi graph có nhiều phiên bản cạnh tranh theo quy tắc kiểm tra của Gradle, lệnh có thể **fail thay vì tự hòa giải**. Đây là cách phát hiện vấn đề, không phải cách ép chọn 3.12.0 hay 3.14.0.

Đừng bật global failOnVersionConflict trên tất cả configurations trong dự án lớn rồi coi mọi conflict transitive là sai ngay: nhiều thư viện có các version requests khác nhau mà việc chọn phiên bản phù hợp cần được phân tích cụ thể.

### 4.4. componentSelection

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.componentSelection {
        all { selection ->
            if (selection.candidate.group == 'com.example' &&
                selection.candidate.module == 'codec' &&
                selection.candidate.version == '2.0.0') {
                selection.reject('Phiên bản này bị lỗi')
            }
        }
    }
}
~~~

Tọa độ com.example chỉ minh họa DSL. Rule này **loại một candidate version**, không hứa có version khác để chọn. Nếu không còn lựa chọn hợp lệ, resolution có thể thất bại.

### 4.5. dependencySubstitution

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.dependencySubstitution {
        substitute(module('com.example:legacy-api'))
            .using(module('com.example:new-api:2.0.0'))
            .because('Thay thế component đã ngừng hỗ trợ')
    }
}
~~~

Đây là **snippet minh họa** với các module giả định. Nó thay một **component request** bằng component khác, có thể đổi group/name, không đơn thuần ép version như force. Composite builds cũng dùng dependency substitution để chuyển từ external module sang project trong included build.

### 4.6. Dynamic/changing versions

Gradle có thể chặn graph không tái lập:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.failOnDynamicVersions()
    resolutionStrategy.failOnChangingVersions()
}
~~~

Các lựa chọn như 1.+ hoặc latest.release có thể khiến resolved version thay đổi theo repository/time; changing modules còn có thể thay artifact/metadata cùng tọa độ. Force một version của một module **không khóa toàn bộ graph** và không thay cho locking/verification.

## 5. Bài thực hành Java 17: compile dùng 3.14, runtime bị ép 3.12

Bài lab độc lập, dùng **Gradle Groovy DSL**, Java 17 và hai versions thật của Apache Commons Lang trên Maven Central. Không dùng thư viện giả định trong mã có thể chạy.

### 5.1. Cấu trúc dự án

~~~text
resolution-strategy-lab/
├── settings.gradle
├── build.gradle
├── gradlew                # tạo bằng Gradle Wrapper
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/Main.java
~~~

Cần JDK 17 hoặc toolchain 17 được provision đúng, Gradle tương thích với môi trường, và kết nối mạng để resolve Commons Lang khi cache chưa có. Nếu chưa có Wrapper, dùng một Gradle đã cài chạy **gradle wrapper** một lần trong project, sau đó dùng gradlew/gradlew.bat.

**settings.gradle**

~~~groovy
rootProject.name = 'resolution-strategy-lab'
~~~

### 5.2. build.gradle đầy đủ

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

application {
    mainClass = 'demo.Main'
}

dependencies {
    // Cố ý tạo hai yêu cầu tới cùng module để thấy conflict.
    implementation 'org.apache.commons:commons-lang3:3.12.0'
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}

// CHỈ runtimeClasspath bị ép về 3.12.0.
configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Đây là tình huống **cố ý tạo conflict để học**, không phải cách khai báo dependency nên duy trì trong production. Trong build thực tế nên có nguồn quản lý version rõ ràng, constraints/platform/lock khi phù hợp.

**src/main/java/demo/Main.java**

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        String value = StringUtils.capitalize("gradle");
        System.out.println("message=" + value);
    }
}
~~~

StringUtils.capitalize(String) được hỗ trợ bởi cả Commons Lang 3.12.0 và 3.14.0, nên có thể dùng để quan sát version resolution mà không cố ý gây NoSuchMethodError.

### 5.3. Chạy app

Linux/macOS:

~~~bash
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
~~~

Đầu ra do **Main.main** in, khi dependencies và toolchain được resolve thành công:

~~~text
message=Gradle
~~~

Dòng stdout này **không chứng minh version cuối** vì API được dùng cho kết quả giống nhau trên cả hai versions. Muốn xem version cuối phải dùng Gradle dependency reports.

### 5.4. So sánh hai classpaths

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Trong graph đơn giản của lab, kỳ vọng:

| Configuration | Requested versions | Selected version | Lý do chính |
|---|---|---|---|
| compileClasspath | 3.12.0 và 3.14.0 | **3.14.0** | Conflict resolution thông thường |
| runtimeClasspath | 3.12.0 và 3.14.0 | **3.12.0** | resolutionStrategy.force trên runtimeClasspath |

**Đừng kiểm chứng bằng cách đọc cả hai graph mà chỉ tìm chuỗi 3.12.0:** Gradle report có thể in requested version ở một nhánh cùng ký hiệu chuyển phiên bản; selected version phải được đọc đúng. Format các dòng và lý do có thể thay đổi theo Gradle version.

### 5.5. dependencyInsight giải thích vì sao

~~~bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration compileClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
~~~

Ở compileClasspath, xem version **3.14.0** được chọn do yêu cầu cạnh tranh. Ở runtimeClasspath, xem version **3.12.0** và selection reason như **Forced**. Nếu có nhiều selection reasons, báo cáo có thể hiển thị nhiều lý do cùng lúc.

Trong các dự án phức tạp, dependencyInsight quan trọng hơn phỏng đoán từ số dòng implementation, vì selected version còn bị ảnh hưởng bởi constraints, BOM/platform, transitive requests, attributes và custom rules.

### 5.6. Thí nghiệm A: bỏ force

Tạm comment hoặc xóa **duy nhất block force** trong ví dụ:

~~~groovy
// configurations.named('runtimeClasspath') {
//     resolutionStrategy.force(
//         'org.apache.commons:commons-lang3:3.12.0'
//     )
// }
~~~

Chạy:

~~~bash
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew -q run
~~~

Với graph đơn giản trong lab, runtimeClasspath sẽ chọn **3.14.0** theo conflict resolution bình thường. Main vẫn in:

~~~text
message=Gradle
~~~

Khôi phục block force nếu muốn dùng baseline ban đầu. Bạn **không phải** xóa ~/.gradle/caches để thay resolution rule trong build.gradle.

### 5.7. Thí nghiệm B: chỉ ép compileClasspath

Thay rule bằng:

~~~groovy
configurations.named('compileClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Đảm bảo **không còn force trên runtimeClasspath**. Bây giờ compileClasspath chọn **3.12.0** và runtimeClasspath của lab chọn **3.14.0**. Đây là hình ảnh đảo chiều của baseline và chứng minh force gắn với configuration.

### 5.8. Thí nghiệm C: ép toàn project

Thay thế bằng:

~~~groovy
configurations.configureEach {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Cả compileClasspath và runtimeClasspath của project này sẽ bị ép 3.12.0 nếu module xuất hiện trong graph tương ứng. Nhưng các test/tool configurations khác cũng có thể bị ảnh hưởng. Đừng mặc định “configureEach” nghĩa là “chỉ cấu hình khi chạy run”.

### 5.9. Thí nghiệm D: ép phiên bản không tồn tại

Chỉ để thấy lỗi, thay version forced bằng:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:99.99.99'
    )
}
~~~

Vì 99.99.99 không có trên repository được sử dụng, khi resolve runtimeClasspath, Gradle sẽ báo không thể tìm module/artifact phù hợp. Force **không tải được phiên bản không tồn tại**. Khôi phục 3.12.0 sau thí nghiệm.

### 5.10. Thí nghiệm E: phát hiện conflict thay vì ép

Bỏ tất cả force, dùng:

~~~groovy
configurations.named('runtimeClasspath') {
    resolutionStrategy.failOnVersionConflict()
}
~~~

Hai version requests ở lab tạo conflict rõ ràng; lệnh resolve graph có thể báo lỗi version conflict thay vì tự chọn 3.14.0. Dùng khi bạn muốn phát hiện các nâng phiên bản bất ngờ, không phải khi muốn “đảm bảo chạy 3.12.0”.

**Mỗi thí nghiệm là một phương án thay thế build.gradle.** Không ghép cả force ở compile, force ở runtime, eachDependency, strictly và failOnVersionConflict rồi kỳ vọng kết quả của từng phương án độc lập vẫn đúng.

## 6. Scope trong multi-project build: consumer có thể chọn khác producer

Giả sử:

~~~text
root
├── core/build.gradle
└── app/build.gradle
~~~

**core/build.gradle (snippet):**

~~~groovy
plugins {
    id 'java-library'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

**app/build.gradle (snippet):**

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':core')
}

configurations.named('runtimeClasspath') {
    resolutionStrategy.force(
        'org.apache.commons:commons-lang3:3.12.0'
    )
}
~~~

Ví dụ giả định settings.gradle đã include('core', 'app') và có JDK/toolchain thích hợp; các đoạn trên là **snippets**, không phải toàn bộ dự án chạy được như lab ở mục 5.

**Hiểu đúng:**

- :core compile bằng compileClasspath của core và có thể chọn Commons Lang **3.14.0**.
- :app runtimeClasspath chứa những transitive dependencies phù hợp do :core cung cấp.
- Force của :app runtimeClasspath có thể ép Commons Lang **3.12.0 trong graph runtime của app**.
- Nó **không sửa** dependency declaration trong core và không ép core:compileClasspath.
- Một thư viện được biên dịch với method chỉ có ở 3.14.0 có thể bị lỗi khi chạy trên 3.12.0.

Tương tự, :app force không ảnh hưởng graph của module :tool chỉ vì hai modules ở cùng repository. Để áp policy tại nhiều projects, cần cấu hình tại từng project hoặc áp convention plugin chung.

## 7. Đổi version trong resolution không đồng nghĩa quản lý version lâu dài

### 7.1. Version catalog

Version catalog (libs.versions.toml) giúp tập trung những tọa độ/versions **được yêu cầu** trong build script. Nó **không tự** có nghĩa là selected version cuối của một module luôn đúng với một alias trong catalog, vì transitive requests/constraints vẫn tham gia resolution.

### 7.2. Dependency constraints và platform

Constraints biểu đạt yêu cầu phiên bản trong graph. Một Java library có thể publish constraints qua **Gradle Module Metadata** cho consumers của mình. Platform có thể gom constraints tương thích của nhiều modules.

Một **enforcedPlatform** mạnh hơn platform thường và có thể ảnh hưởng consumers; nếu library publish enforcedPlatform, cần đánh giá rất kỹ vì ép phiên bản có thể lan theo dependency graph. Đừng thay một local force bằng enforcedPlatform chỉ vì muốn “force xuyên project” mà chưa hiểu metadata.

### 7.3. Dependency locking

Locking ghi lại resolved versions cho các configurations được quản lý, giúp tái lập graph giữa máy developer và CI. Force một module không thể thay thế việc locking cả dependency graph. Khi thay đổi dependency requirements hoặc forced versions, cần cập nhật lock state theo quy trình có review.

### 7.4. Dependency verification

Verification xác thực artifact và metadata theo checksum/signature policy. Force chọn version không chứng minh artifact ấy an toàn hoặc đúng publisher. Đối với supply-chain security, nên dùng repository policy, dependency verification và version upgrade procedures.

### 7.5. Version range, dynamic và changing module

Các yêu cầu như 1.+ hoặc latest.release có thể đổi selected version theo thời điểm/repository. Changing modules có thể giữ version nhưng thay artifact/metadata. Force một version cho một graph không biến mọi yêu cầu khác thành immutable.

Nếu mục tiêu là reproducibility, hãy quản lý **cả graph** bằng declarations/constraints/locking/verification, không chỉ force một thư viện.

## 8. Quy tắc chọn công cụ theo mục tiêu

| Nhu cầu | Giải pháp ưu tiên |
|---|---|
| Một module thiếu trong graph | Thêm dependency vào configuration phù hợp |
| Hai phiên bản cạnh tranh, chưa biết cái nào đúng | dependencies + dependencyInsight |
| Cần fail ngay khi conflict xuất hiện | failOnVersionConflict() |
| Cần hạ một module transitive trong một runtime graph để debug | force(...) **hẹp theo configuration** |
| Version thuộc public library contract | Dependency constraints/strictly/platform phù hợp |
| Muốn kiểm soát toàn bộ versions đã resolve trên CI | Dependency locking |
| Muốn kiểm tra artifact đúng checksum | Dependency verification |
| Muốn loại một module/version lỗi | Constraints/reject hoặc componentSelection khi phù hợp |
| Muốn đổi group/name/module khác | dependencySubstitution / module replacement |
| Muốn đổi external module thành source project | Project dependency hoặc composite build/substitution |
| Muốn compile và runtime chọn cùng version | Quản lý declarations/constraints trên **các graph liên quan**, kiểm tra cả hai |
| Muốn fix plugin resolution | Kiểm tra pluginManagement/buildscript classpath; không sửa app runtime force |

**Khuyến nghị:** Force chỉ nên là **một quyết định rõ lý do**, có phạm vi, có kiểm chứng và có kế hoạch gỡ bỏ nếu dùng làm workaround.

## 9. Chẩn đoán bằng công cụ Gradle

### 9.1. Quy trình tối thiểu

1. Xác định project và task lỗi: compileJava, run, test hoặc custom task.
2. Tìm **resolvable configuration** task sử dụng.
3. Chạy dependencies --configuration ... cho đúng project/configuration.
4. Chạy dependencyInsight của module nghi vấn; xem **requested → selected** và selection reason.
5. Đọc force/eachDependency/strictly/platform/lock đang áp lên graph đó.
6. Xác minh version được chọn thực sự tồn tại trong repositories.
7. Kiểm thử binary compatibility nếu runtime thấp hơn compile.
8. Thu hẹp/gỡ rule sau khi đã chữa nguyên nhân gốc.

### 9.2. Lệnh một project

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration compileClasspath
./gradlew -q run
~~~

### 9.3. Lệnh multi-project

~~~bash
./gradlew :core:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
~~~

Không lấy :core:compileClasspath làm bằng chứng rằng :app:runtimeClasspath sẽ chọn cùng version. Chúng là hai graphs có thể chịu resolution rules khác nhau.

### 9.4. Phân biệt với command-line flags

- **--refresh-dependencies** yêu cầu Gradle kiểm tra lại dependency metadata/artifacts trong những trường hợp phù hợp; nó **không xóa** force trong build.gradle.
- **--rerun-tasks** buộc tasks thực thi lại và bỏ qua một số tối ưu cho task execution; nó **không thay** selected version do force.
- **--offline** yêu cầu resolve bằng cache cục bộ khi có thể; nếu forced version chưa có trong cache, có thể thất bại.
- **clean** xóa build outputs được task clean quản lý; nó không sửa force rule hoặc tự thay versions của graph.

Nếu muốn một version khác, phải sửa dependency declarations/constraints/rules phù hợp, rồi xác minh bằng dependencyInsight.

## 10. Lỗi phổ biến và cách giải quyết

### Lỗi 1: Force ở implementation nhưng runtimeClasspath không đổi

**Nguyên nhân:** implementation là bucket khai báo; không nên cho rằng resolutionStrategy trên bucket tự được kế thừa bởi các resolvable configurations.

**Cách sửa:** Đặt rule trực tiếp ở runtimeClasspath/compileClasspath hoặc dùng configureEach khi bạn thật sự muốn phạm vi rộng.

### Lỗi 2: Force một module nhưng Gradle không tải nó

**Nguyên nhân:** Force **không thêm dependency**. Không có request đến module, rule không làm module xuất hiện.

**Cách sửa:** Thêm implementation/runtimeOnly/testImplementation thích hợp hoặc để module được kéo từ transitive graph.

### Lỗi 3: Force ở root nhưng subproject không bị ép

**Nguyên nhân:** Root và subproject có những Configurations container khác nhau.

**Cách sửa:** Đặt rule ở đúng project hoặc áp convention plugin cho những subprojects cần chính sách đó.

### Lỗi 4: Biên dịch thành công, chạy ném NoSuchMethodError

**Nguyên nhân có thể:** CompileClasspath chọn version mới nhưng runtimeClasspath bị force xuống bản cũ, hoặc transitive binary yêu cầu API mới.

**Cách sửa:** So sánh selected versions ở compile/runtime, kiểm tra public API/ABI của dependency, chạy integration tests và điều chỉnh constraints/declarations phù hợp. Không coi resolution success là compatibility guarantee.

### Lỗi 5: Force một version không tồn tại

**Nguyên nhân:** Repository không có module/version hoặc credentials/network/cache không đáp ứng.

**Cách sửa:** Kiểm tra group/name/version, repository, offline status và quyền truy cập; force không thể tạo artifact.

### Lỗi 6: Có strictly nhưng version cuối vẫn bị hạ

**Nguyên nhân:** ResolutionStrategy.force có thể override strictly constraints trong graph.

**Cách sửa:** Xem selection reasons và giảm local overrides, kiểm thử compatibility. Với published libraries, ưu tiên constraints/strictly biểu đạt version intent.

### Lỗi 7: Mỗi module trong build dùng version khác

**Nguyên nhân:** ResolutionStrategy thuộc **từng project + configuration**, không phải một graph toàn build.

**Cách sửa:** Rà soát graph của từng consumer, áp convention plugin khi cần, hoặc quản trị chung bằng platform/constraints/locking. Đừng giả định force của một module tác động ngược lại build graph của module khác.

### Lỗi 8: Force quá rộng làm hỏng test/annotation processor

**Nguyên nhân:** configurations.configureEach áp rule cho nhiều configurations hơn dự kiến.

**Cách sửa:** Thu hẹp vào những resolvable configurations cần can thiệp. Kiểm tra dependencyInsight của testRuntimeClasspath/annotationProcessor khi có dấu hiệu lỗi.

### Lỗi 9: Dùng force để thay com.old:api thành com.new:api

**Nguyên nhân:** Force chọn **version của một module identity**, không đổi group/name/module.

**Cách sửa:** Dùng dependency substitution hoặc module replacement khi phù hợp.

### Lỗi 10: Library publish nhưng consumer không thấy force

**Nguyên nhân:** ResolutionStrategy của build local không được publish như một dependency constraint.

**Cách sửa:** Dùng constraints/platform và kiểm tra POM/Gradle Module Metadata từ consumer thực tế.

### Lỗi 11: Dùng eachDependency và force chồng nhau

**Nguyên nhân:** Nhiều resolution rules có thể xử lý cùng requests; kết quả khó suy luận chỉ từ thứ tự văn bản.

**Cách sửa:** Loại bỏ rules trùng chức năng, ghi rõ because/rationale và kiểm tra selected version ở dependencyInsight thay vì tự đoán.

### Lỗi 12: Rule thêm sau khi configuration đã resolve

**Nguyên nhân:** Build logic khác resolve configuration quá sớm trước khi đăng ký resolution rule.

**Cách sửa:** Cấu hình rules trước khi resolution xảy ra; tránh eager resolution tại configuration phase và ưu tiên lazy APIs.

### Lỗi 13: Cố sửa mọi vấn đề bằng --refresh-dependencies

**Nguyên nhân:** Nhầm chuyện cache metadata với chuyện resolution rule chọn version.

**Cách sửa:** Chỉ dùng --refresh-dependencies khi nghi metadata cache cần kiểm tra lại; nếu forced version sai, sửa force/constraints.

### Lỗi 14: Runtime có hai file JAR chứa cùng class

**Nguyên nhân:** File dependencies không có module identity để Gradle version-conflict resolve giống external modules.

**Cách sửa:** Làm sạch classpath, loại JAR trùng và chuyển file dependency thành module có metadata khi khả thi. Force external module không giải quyết mọi duplicate classes.

## 11. Checklist khi review rule mới

1. Xác định **đúng project** và **đúng configuration** được resolve.
2. Ghi lại requested và selected versions **trước** khi sửa.
3. Xác nhận module có trong graph; force không thêm dependency.
4. Đọc selection reason bằng dependencyInsight.
5. Xem dependency trực tiếp **và transitive** cùng constraints/variants.
6. Đánh giá binary compatibility nếu runtime bị ép xuống dưới compile version.
7. Tránh cấu hình toàn project khi chỉ một runtime graph cần can thiệp.
8. Dùng constraints/platform cho version intent dài hạn khi phù hợp.
9. Xem xét locking/verification cho CI/release reproducibility và supply chain.
10. Đừng nhầm plugin classpath với application classpath.
11. Kiểm thử compile, run, test và những integration paths thực sự bị ảnh hưởng.
12. Ghi comment lý do, phiên bản cũ/mới, người phụ trách và thời điểm gỡ workaround.
13. Xác minh build từ môi trường sạch, không dựa ngẫu nhiên vào cache.
14. Không thay thế conflict diagnosis bằng một rule force không rõ nguyên nhân.

## 12. Bài tập tự kiểm tra

**Bài 1.** Một build khai báo Commons Lang 3.12.0 và 3.14.0, không có constraints/rules khác. Thường Gradle chọn version nào?

**Bài 2.** Force 3.12.0 trên runtimeClasspath có tự làm compileClasspath dùng 3.12.0 không?

**Bài 3.** Graph không yêu cầu Commons Lang. Chỉ có resolutionStrategy.force('org.apache.commons:commons-lang3:3.12.0') thì JAR có tự được thêm vào classpath không?

**Bài 4.** Vì sao force ở :app runtimeClasspath có thể ảnh hưởng transitive Commons Lang từ :core nhưng không đổi :core:compileClasspath?

**Bài 5.** Nếu core đã compile với method chỉ có ở 3.14.0, nhưng app runtime bị ép 3.12.0, có thể xảy ra lỗi gì?

**Bài 6.** Root project dùng configurations.configureEach. Điều này có tự áp rule tới :app và :core không?

**Bài 7.** Bạn muốn một library publish ràng buộc version cho consumer. Nên chỉ dùng local force hay công bố dependency constraint?

**Bài 8.** Mục tiêu là thay com.old:api bằng com.new:api. Nên dùng force hay dependencySubstitution?

**Bài 9.** Muốn Gradle fail nếu có conflict thay vì tự chọn version, dùng rule nào?

**Bài 10.** Làm sao xem lý do selected version ghi Forced?

**Bài 11.** Vì sao --rerun-tasks không bỏ được force khỏi dependency resolution?

**Bài 12.** Bạn muốn build CI dùng cùng resolved versions và xác minh artifact checksum. Hai cơ chế nào giúp hơn là force từng module?

**Bài 13.** strictly('3.14.0') có bảo đảm một configuration force('...:3.12.0') không thể ghi đè không?

**Bài 14.** Vì sao nên tránh force trên mọi configuration khi chỉ cần kiểm thử production runtime?

**Bài 15.** Một module 99.99.99 chưa được publish bị ép qua force. Xóa Gradle cache có tạo version đó không?

### Gợi ý đáp án

1. Với graph đơn giản nêu trên, **3.14.0**.
2. **Không**; mỗi configuration có resolution strategy riêng.
3. **Không**; force không thêm request mới.
4. :app resolve graph của consumer chứa transitive dependencies; :core compile là graph độc lập.
5. Có thể **NoSuchMethodError** hoặc một lỗi ABI tương tự.
6. **Không**; chỉ root configurations được cấu hình.
7. **Dependency constraints/strictly/platform** phù hợp với nhu cầu công bố version intent.
8. **dependencySubstitution** hoặc module replacement.
9. **failOnVersionConflict()**.
10. **dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath** trong đúng project.
11. --rerun-tasks tác động task execution, không xóa resolution rule.
12. **Dependency locking và dependency verification**.
13. **Không**; force của consuming configuration có thể override strictly.
14. Rule rộng có thể làm hỏng test/processor/tool classpaths không liên quan.
15. **Không**; cần chọn version thực sự được publish và resolve được.

## Tài liệu chính thức

- [Gradle User Manual — Using Resolution Rules](https://docs.gradle.org/current/userguide/resolution_rules.html): forcing, dependency rules, substitution và conflict checks.
- [Gradle DSL — ResolutionStrategy](https://docs.gradle.org/current/dsl/org.gradle.api.artifacts.ResolutionStrategy.html): force, forcedModules, eachDependency, failOnVersionConflict, preferProjectModules.
- [Gradle User Manual — Declaring Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): strictly/prefer, precedence và trường hợp resolution strategy override.
- [Gradle User Manual — Rich Versions](https://docs.gradle.org/current/userguide/rich_versions.html): strictly, prefer, reject và yêu cầu version.
- [Gradle User Manual — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html): graph resolution, artifact resolution và variants.
- [Gradle User Manual — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencies, dependencyInsight, selection reasons.
- [Gradle User Manual — Dependency Configurations](https://docs.gradle.org/current/userguide/declaring_configurations.html): scope và vai trò của configurations.
- [Gradle User Manual — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): resolved versions và lock state.
- [Gradle User Manual — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/signature và provenance.

**Ghi nhớ:** **ResolutionStrategy thuộc về một configuration**, force ép version của một module trong **graph được resolve**, không tự thêm module hoặc tự lan toàn build. Chọn đúng **project + configuration**, xem **requested/selected/Forced** bằng dependencyInsight, và ưu tiên constraints, platform, locking, verification khi quản lý dependencies dài hạn.