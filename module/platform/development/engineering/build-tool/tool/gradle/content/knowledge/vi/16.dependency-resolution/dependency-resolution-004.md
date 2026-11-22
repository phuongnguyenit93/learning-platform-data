# Dependency constraints và rich versions: strictly, prefer, reject trong Gradle

## 1. Bài toán: ai quyết định phiên bản dependency cuối cùng?

Một ứng dụng Java có thể dùng trực tiếp `org.apache.commons:commons-lang3`, nhưng một thư viện khác trong cây dependency cũng có thể yêu cầu cùng module ở phiên bản khác. Gradle cần tạo **dependency graph nhất quán** cho từng classpath, lựa chọn component/version và variant phù hợp trước khi các task biên dịch/chạy nhận được file JAR.

Giả sử có các yêu cầu:

~~~text
Ứng dụng
  |
  +-- Module A -> library-x:1.2
  |
  +-- Module B -> library-x:1.8
  |
  +-- Quy tắc tổ chức: library-x không được dùng bản 1.5
~~~

Câu hỏi cần trả lời không chỉ là "phiên bản nào cao nhất?" mà còn là:

- Module nào đang thực sự có trong graph?
- Version do dependency khai báo là mức tối thiểu hay yêu cầu không được thay đổi?
- Có constraint nào đưa ra **phiên bản bắt buộc**, **phiên bản ưu tiên**, hoặc **phiên bản bị cấm**?
- Có platform/BOM, component metadata, variant attributes hoặc dependency lock tác động tới kết quả không?
- Nếu các yêu cầu không tương thích thì Gradle nên thất bại, hay nên tự chọn phiên bản khác?

**Dependency constraints** cho phép mô tả yêu cầu về một module **mà không nhất thiết thêm module đó thành dependency trực tiếp**. **Rich versions** diễn đạt tinh vi hơn một chuỗi version đơn, thông qua các thao tác như `require`, `strictly`, `prefer` và `reject`.

Mục tiêu bài này: hiểu ý nghĩa của từng mức ràng buộc, viết Kotlin DSL/Groovy DSL đúng, đọc báo cáo resolution, xử lý xung đột, áp dụng có kiểm soát và tránh nhầm constraints với force, dependency locking hoặc verification.

## 2. Các khái niệm nền tảng trước khi viết constraint

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Dependency declaration** | Yêu cầu một module tham gia graph | `implementation("g:a:1.0")` |
| **Dependency constraint** | Ràng buộc phiên bản/metadata của module **nếu module đó xuất hiện** trong graph | `constraints { implementation("g:a") { version { strictly("1.5") } } }` |
| **Version constraint** | Điều kiện chọn phiên bản có thể gồm require/strictly/prefer/reject | `version { prefer("1.5") }` |
| **Dependency resolution** | Gradle xây graph, giải quyết yêu cầu, chọn component/version/variant | Giải quyết `runtimeClasspath` |
| **Transitive dependency** | Dependency được đưa vào bởi module khác | A cần B; B cần C |
| **Conflict resolution** | Hòa giải các yêu cầu khác phiên bản của cùng module, hoặc thất bại khi không tương thích | A yêu cầu 1.2, B yêu cầu 1.8 |
| **Dependency insight** | Báo cáo tại sao một dependency/version được chọn | `dependencyInsight` |
| **Dependency locking** | Ghi phiên bản đã chọn để lần sau tái lập graph | `gradle.lockfile` |
| **Dependency verification** | Kiểm tra checksum/chữ ký artifact/metadata được chấp nhận | `verification-metadata.xml` |

Một dependency declaration có thể dùng phiên bản đơn giản:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.12.0")
}
~~~

Với các version thông thường được ghi theo dạng `group:module:version`, Gradle xem đây là một **yêu cầu phiên bản** chứ không mặc định là khóa cứng không cho nâng. Nếu có yêu cầu khác mạnh hơn hoặc quá trình conflict resolution, phiên bản được chọn có thể khác `3.12.0`.

**Đừng coi khai báo version là bằng chứng runtime đang dùng đúng version đó.** Hãy xem graph đã resolve qua `dependencies` hoặc `dependencyInsight`.

## 3. Dependency constraints: ràng buộc nhưng không tự thêm thư viện

Một constraint nói "nếu module này nằm trong graph, áp dụng quy tắc phiên bản này", chứ không phải "hãy đưa module này vào graph".

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                strictly("3.17.0")
            }
            because("Ví dụ chính sách phiên bản được phê duyệt")
        }
    }
}
~~~

Ở đây:

1. `constraints { ... }` mở container khai báo dependency constraints.
2. `implementation(...)` là tên configuration mang constraint. Nó không phải lời gọi thêm dependency trực tiếp ở cấp ngoài.
3. `version { strictly("3.17.0") }` yêu cầu dùng phiên bản phù hợp ràng buộc nghiêm ngặt khi module hiện diện.
4. `because(...)` diễn giải **lý do** cho người đọc và báo cáo Gradle. Nó không phải cơ chế bảo mật hay thuật toán chọn version.
5. Nếu project **không có dependency nào** đưa `commons-lang3` vào classpath cần xét, riêng constraint trên không tự khiến Gradle tải JAR đó.

Muốn có dependency thực sự, cần một declaration:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.12.0")
}
~~~

Sau đó constraint trên có thể tác động đến version cuối cùng của module đó khi resolution. Không được nhầm `constraints { implementation(...) }` với `implementation(...)` trực tiếp bên ngoài khối constraints.

### 3.1. Vì sao cần constraint thay vì sửa mọi declaration?

Trong multi-project build, có thể hàng chục module yêu cầu cùng một thư viện qua các đường transitive khác nhau. Một constraint tập trung giúp:

- đặt minimum/strict version hoặc chặn phiên bản lỗi đã biết;
- giải thích chính sách qua `because`;
- tách ý định "cần thư viện" khỏi ý định "khi thư viện có mặt thì phiên bản nào chấp nhận được";
- tránh tạo một dependency mới ở những module không cần nó;
- tổ chức thông tin phiên bản trong platform hoặc convention plugin phù hợp.

Nhưng phạm vi của constraint phụ thuộc **configuration/source set/project** chứa nó và quan hệ kế thừa của configuration. Một constraint trong `testImplementation` không tự động quyết định mọi classpath của toàn build. Cần áp dụng đúng các configuration thật sự resolve module.

## 4. Bốn thao tác version cốt lõi

Gradle hỗ trợ các ý nghĩa sau trong rich versions:

| API | Ý nghĩa thực tế | Độ mạnh tương đối |
| --- | --- | --- |
| `require("1.5")` | Yêu cầu phiên bản đáp ứng điều kiện; với một version thông thường, bản cao hơn vẫn có thể được chọn qua conflict resolution | Ràng buộc bắt buộc nhưng có thể nâng theo yêu cầu hợp lệ |
| `strictly("1.5")` | Chỉ chấp nhận phiên bản đáp ứng ràng buộc **nghiêm ngặt**; với version cố định `1.5`, phiên bản khác bị loại trừ trừ trường hợp cơ chế điều chỉnh đặc biệt | Mạnh; có thể khiến resolution fail khi xung đột |
| `prefer("1.5")` | Bày tỏ **ưu tiên** khi không có yêu cầu mạnh hơn quyết định kết quả | Mềm; có thể bị ghi đè bởi yêu cầu mạnh hơn |
| `reject("1.4")` | Loại phiên bản (hoặc selector) khỏi các ứng viên có thể chọn | Loại ứng viên; không tự chọn phiên bản thay thế |

Ngoài ra còn có `rejectAll()`, dùng để từ chối mọi phiên bản trong context tương ứng; không nên dùng tùy tiện vì thường dẫn tới việc không thể resolve nếu không có logic khác.

Hãy đọc nguyên tắc này:

- **require**: "tôi cần phiên bản tối thiểu/phạm vi đáp ứng điều kiện này".
- **strictly**: "tôi không chấp nhận vượt ngoài phiên bản hoặc phạm vi này".
- **prefer**: "tôi muốn dùng phiên bản này nếu những ràng buộc còn lại cho phép và không có yêu cầu mạnh hơn".
- **reject**: "tôi không chấp nhận ứng viên này, dù nó có vẻ là phiên bản mới hơn".

Với version range hoặc dynamic selector, phải đọc **cú pháp selector** thay vì giả định tất cả bốn API luôn nhận một số phiên bản đơn giản. Ví dụ `strictly("[1.5,2.0)")` là ràng buộc range nghiêm ngặt, không đồng nghĩa pin cố định 1.5.

### 4.1. “Mạnh hơn” không phải là quy tắc chọn phiên bản đơn giản duy nhất

Gradle còn xem các dependency requests khác, metadata, variant attributes, capabilities, constraints được mang theo, platform và chính sách resolution. Phương pháp "nếu có strictly thì luôn thắng mọi cơ chế" là **quá đơn giản và có thể sai**, đặc biệt khi build có `force` hoặc component selection rules được cấu hình khác thường.

Quy tắc an toàn: coi một constraint nghiêm ngặt là **điều kiện về tính hợp lệ của phiên bản được chọn**; nếu không có phiên bản thỏa được toàn bộ các điều kiện tương thích, resolution nên báo lỗi. Đọc kết quả thật bằng `dependencyInsight` thay vì dựa vào thứ tự dòng trong DSL.

## 5. Ví dụ chạy được: phiên bản khai báo 3.12.0, chọn 3.17.0 bởi strictly

Demo này dùng Gradle Kotlin DSL + Java 17+ và dependency thật `org.apache.commons:commons-lang3`. Kết quả minh họa cách constraint có thể điều chỉnh một version yêu cầu thấp hơn.

### 5.1. Cấu trúc dự án

~~~text
rich-versions-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/main/java/demo/Main.java
~~~

Cần một Gradle Wrapper tương thích JDK 17+ và có quyền truy cập Maven Central hoặc mirror hợp lệ. Các file Wrapper thường được tạo bằng Gradle hoặc từ project mẫu; sơ đồ trên không có nghĩa chỉ cần tự tạo file `gradlew` trống.

**`settings.gradle.kts`:**

~~~kotlin
rootProject.name = "rich-versions-demo"
~~~

**`build.gradle.kts`:**

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.12.0")

    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                strictly("3.17.0")
            }
            because("Ví dụ minh họa strict version constraint")
        }
    }
}

application {
    mainClass.set("demo.Main")
}
~~~

**`src/main/java/demo/Main.java`:**

~~~java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(StringUtils.capitalize("gradle constraints"));
    }
}
~~~

Trong build này, `application` cung cấp Java compilation/runtime tasks; `implementation` khai báo thư viện được sử dụng. Constraint nghiêm ngặt chỉ rõ 3.17.0, trong khi declaration 3.12.0 không được coi là pin bất biến.

### 5.2. Chạy ứng dụng

Linux/macOS:

~~~bash
./gradlew -q run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q run
~~~

Dòng stdout của **chương trình Java**:

~~~text
Gradle constraints
~~~

Các log khác phụ thuộc môi trường, plugin, version Gradle và repository. Nếu không tải được dependency từ Maven Central thì lỗi mạng/repository sẽ xảy ra trước khi chương trình chạy.

### 5.3. Kiểm tra version thực tế bằng dependencyInsight

~~~bash
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency commons-lang3 \
  --console=plain
~~~

PowerShell dùng một dòng:

~~~powershell
.\gradlew.bat dependencyInsight --configuration runtimeClasspath --dependency commons-lang3 --console=plain
~~~

Khi resolution thành công, báo cáo phải cho thấy **module `commons-lang3` được chọn ở phiên bản `3.17.0`**, còn yêu cầu trực tiếp ban đầu tham chiếu 3.12.0. Định dạng báo cáo, đường nối `3.12.0 -> 3.17.0` và lý do lựa chọn khác nhau theo phiên bản Gradle; đừng coi một chuỗi log cụ thể là output bất biến.

**Điểm quan trọng:** in ra `Gradle constraints` chỉ chứng minh mã Java chạy, **không chứng minh version 3.17.0 bằng mắt thường**. Muốn xác minh phiên bản resolved, dùng `dependencyInsight` hoặc báo cáo graph theo đúng configuration.

## 6. strictly: khi nào dùng và điều gì xảy ra nếu xung đột?

`strictly("3.17.0")` thể hiện ràng buộc nghiêm ngặt đối với một version cụ thể. Nó hữu ích khi:

- tổ chức cần phiên bản được kiểm thử và phê duyệt, chưa cho tự nâng;
- một bản khác không tương thích binary/API và cần fail sớm;
- có yêu cầu tuân thủ hoặc rủi ro nghiêm trọng ở những phiên bản không được chấp nhận;
- đang thực hiện migration theo nhiều bước và muốn giữ một dependency trong phạm vi an toàn.

Ví dụ rich version ngay trên dependency:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3") {
        version {
            strictly("3.17.0")
        }
        because("Ứng dụng đã kiểm thử với bản này")
    }
}
~~~

Đây là **đoạn thay thế** cho dependency declaration ở mục 5, không phải thêm đồng thời hai bản chỉ để học. Khi module này tham gia graph, Gradle có constraint nghiêm ngặt đối với version được chọn.

### 6.1. Hai yêu cầu nghiêm ngặt không tương thích

Giả sử cùng một graph có hai yêu cầu:

~~~text
A: strictly("3.14.0")
B: strictly("3.17.0")
~~~

Không có một version cố định nào thỏa **cả hai**. Trong cấu hình thông thường, dependency resolution sẽ **thất bại** thay vì âm thầm chọn bản mới nhất. Đây là một lợi ích: build nói rõ ý định của các bên không tương thích.

Nếu thấy một lỗi như “Cannot find a version ... that satisfies the version constraints”, cần:

1. xác định module và configuration đang resolve;
2. tìm nguồn từng constraint/dependency (trực tiếp, transitive, platform, plugin);
3. quyết định phiên bản/range nào thực sự được phép;
4. nâng cấp hoặc thay đổi dependency gây xung đột;
5. chạy lại báo cáo cho đúng classpath.

**Không sửa bằng cách vô hiệu hóa toàn bộ constraints** hoặc dùng `force` để giấu xung đột chưa hiểu. Force và resolution rules có thể thay đổi cách chọn version, nhưng thường làm ý định của metadata/constraints khó quan sát hơn.

### 6.2. strictly có thể nhận range

~~~kotlin
dependencies {
    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                strictly("[3.14.0,4.0)")
                prefer("3.17.0")
            }
            because("Chỉ chấp nhận nhóm 3.x đã được đánh giá")
        }
    }
}
~~~

`[3.14.0,4.0)` nghĩa là chấp nhận từ 3.14.0 trở lên nhưng **không bao gồm 4.0**; `prefer("3.17.0")` đặt một điểm ưu tiên trong phạm vi hợp lệ. Ở đây constraint **không** chỉ cho phép 3.17.0 duy nhất. Nếu xuất hiện version khác thỏa range do các yêu cầu mạnh hơn hoặc quá trình resolution, kết quả không nhất thiết là 3.17.0.

Version ranges có thể làm kết quả build biến đổi khi repository có bản mới; cân nhắc dependency locking khi cần tái lập, và luôn review thay đổi.

## 7. prefer: diễn đạt ý muốn, không phải mệnh lệnh

`prefer` hữu ích khi bạn muốn khuyến nghị một version nhưng để quá trình resolution chọn bản khác khi các yêu cầu bắt buộc không cho phép hoặc khi một phiên bản mạnh hơn được đưa vào graph.

Ví dụ Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.12.0")

    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                prefer("3.17.0")
            }
            because("Ưu tiên bản được nhóm sử dụng gần đây")
        }
    }
}
~~~

Ở đây constraint chỉ bày tỏ **ưu tiên** 3.17.0. Kết quả phụ thuộc các dependency/constraints khác: nếu tồn tại yêu cầu phiên bản khác có độ mạnh cao hơn, Gradle có thể không chọn 3.17.0.

Trường hợp thường thấy:

~~~text
Đường phụ thuộc A -> prefer 1.5
Đường phụ thuộc B -> require 1.8
                 -> version cuối không nhất thiết là 1.5
~~~

Đừng viết `prefer("1.5")` khi chính sách thực chất yêu cầu **cấm** dùng version khác. `prefer` không phải cơ chế hard pin, không thay thế kiểm thử bảo mật hoặc dependency lock.

### 7.1. Phân biệt “mặc định đề xuất” và “cần bản tối thiểu”

- Nếu chỉ muốn một phiên bản mặc định thuận tiện, nhưng cho phép bên khác dùng version hợp lệ: `prefer`.
- Nếu phải đáp ứng một mức tối thiểu hoặc range: `require` hoặc rule thích hợp.
- Nếu phải ở trong một range cố định: `strictly` với range.
- Nếu chỉ chặn một số version cụ thể: `reject`.
- Nếu muốn **chốt toàn bộ graph tái lập**, constraints không tự thay thế dependency locking.

Một bài kiểm tra đúng không chỉ nhìn DSL mà còn chạy `dependencyInsight` khi thêm/bớt transitive dependencies để xác nhận ý định thật.

## 8. reject: từ chối các phiên bản đã biết là không phù hợp

`reject` có tác dụng **loại những version selector được chỉ định khỏi tập ứng viên**. Đó có thể là bản bị lỗi tương thích, bản chưa được phê duyệt hoặc bản có vấn đề bảo mật đã được xác minh.

Ví dụ:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.12.0")

    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                require("[3.12.0,4.0)")
                reject("3.14.0", "3.15.0")
            }
            because("Loại các bản không được chấp nhận theo chính sách demo")
        }
    }
}
~~~

Đây là **snippet Kotlin DSL**; danh sách version bị loại chỉ có tính minh họa, **không phải khuyến cáo bảo mật** rằng 3.14.0/3.15.0 thực sự có lỗ hổng. Muốn loại version vì CVE, phải tra advisory chính thức và phạm vi affected/fixed cụ thể.

Quy tắc:

1. `require("[3.12.0,4.0)")` cho phép một range theo cú pháp Maven, không có nghĩa chốt bản cao nhất một cách bất biến.
2. `reject("3.14.0", "3.15.0")` loại hai version đó khỏi ứng viên hợp lệ.
3. Gradle có thể chọn bản khác **nếu** còn ứng viên thỏa tất cả điều kiện của graph.
4. Nếu mọi ứng viên phù hợp đều bị reject hoặc các ràng buộc không tương thích, resolution có thể **thất bại**.
5. `reject` không tự bảo đảm phiên bản được chọn đã vá mọi CVE: cần phối hợp kiểm tra security advisories, dependency inventory và verification.

### 8.1. reject không tự thêm dependency

~~~kotlin
dependencies {
    constraints {
        implementation("org.example:widget") {
            version {
                reject("1.2.3")
            }
        }
    }
}
~~~

Đây là một **snippet minh họa** với module không được khẳng định có thật. Nếu không có dependency nào yêu cầu `org.example:widget`, constraint không làm Gradle tải `widget`. Nó chỉ có thể tác động nếu module đó xuất hiện trên classpath mà constraint tham gia.

### 8.2. Vì sao reject có thể làm build thất bại thay vì “tự hạ bản”?

Ví dụ:

~~~text
Requested: strictly 2.0
Rejected:  2.0
Candidate: 1.9
~~~

Không thể coi 1.9 là giải pháp mặc định: nó vi phạm `strictly 2.0`. Gradle phải giải quyết yêu cầu mâu thuẫn hoặc báo lỗi; người dùng cần sửa constraint hoặc cập nhật dependency phù hợp.

Tương tự, nếu repository chỉ có một version và bạn reject chính version đó, Gradle không thể suy ra một artifact khác chưa tồn tại.

### 8.3. rejectAll() có vai trò gì?

`rejectAll()` thể hiện từ chối mọi phiên bản trong constraint; đây không phải lựa chọn thông thường để quản lý version. Chỉ dùng khi hiểu rõ mô hình resolution và ý định là làm module không có version nào được chấp nhận trong context ấy. Với đa số dự án, sử dụng `reject` theo những version/range cụ thể sẽ dễ hiểu hơn.

## 9. require: phiên bản yêu cầu không đồng nghĩa với khóa cứng

Dù tiêu đề tập trung `strictly`, `prefer` và `reject`, cần hiểu `require` để đọc đúng bản rich version hoàn chỉnh.

Ví dụ:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3") {
        version {
            require("3.12.0")
        }
    }
}
~~~

Với một version tĩnh, `require("3.12.0")` thể hiện yêu cầu tham gia resolution ở mức version đó; trong trường hợp conflict resolution thông thường, Gradle có thể nâng lên phiên bản cao hơn được yêu cầu/được chấp nhận. Nó **không tương đương** `strictly("3.12.0")`.

So sánh:

| Mã | Điều mong đợi |
| --- | --- |
| `require("3.12.0")` | Yêu cầu version không thấp hơn mức tĩnh đó theo semantics của Gradle, vẫn có thể nâng |
| `strictly("3.12.0")` | Chỉ chấp nhận đúng 3.12.0 trong giải quyết thông thường |
| `prefer("3.12.0")` | Ưu tiên 3.12.0, cho phép yêu cầu mạnh hơn quyết định |
| `reject("3.12.0")` | Không chấp nhận 3.12.0 làm version được chọn |

Với version **range** hoặc **dynamic selector**, chữ “không thấp hơn” không còn mô tả trọn vẹn; phải áp dụng semantics của selector. Ví dụ `require("[3.12.0,4.0)")` nói về khoảng hợp lệ, không phải một số min duy nhất.

**Một lỗi tư duy:** nhóm viết `implementation("module:1.0")` và nghĩ đã khóa 1.0. Nếu cần chắc chắn không nâng, hãy xem `strictly` hoặc dependency locking theo mục đích thực tế; đừng dựa vào version string trơn.

## 10. Ghép rich version trong một khai báo có nghĩa gì?

Gradle hỗ trợ rich version constraint có thể kết hợp ràng buộc mạnh, điểm ưu tiên và danh sách loại trừ. Ví dụ:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3") {
        version {
            strictly("[3.12.0,4.0)")
            prefer("3.17.0")
            reject("3.14.0")
        }
        because("Giữ phạm vi tương thích, ưu tiên bản đã kiểm thử")
    }
}
~~~

Đây là một cấu hình có chủ ý:

- **Phạm vi cứng:** không dưới 3.12.0 và không đến 4.0.
- **Điểm ưu tiên:** 3.17.0.
- **Ngoại lệ:** không dùng 3.14.0, dù nó nằm trong range.
- **Lý do:** ghi chú cho developer và báo cáo.

Nhưng kết quả **không nhất thiết** là 3.17.0 trong mọi graph: các yêu cầu từ dependencies/platform khác có thể buộc lựa chọn một version khác trong phạm vi hoặc khiến resolution fail. Hãy dùng `dependencyInsight`.

### 10.1. Không nên tạo constraint tự mâu thuẫn

Ví dụ phải tránh:

~~~kotlin
version {
    strictly("3.17.0")
    reject("3.17.0")
}
~~~

Bạn vừa tuyên bố chỉ chấp nhận 3.17.0 vừa loại 3.17.0. Khi module xuất hiện trong graph, không có version đáp ứng đồng thời hai điều kiện. Đừng cố "sửa" bằng cách thêm một `prefer` khác; hãy quyết định chính sách và phiên bản thực sự hợp lệ.

### 10.2. Đừng dùng nhiều lệnh strict khác nhau như điều kiện OR

Khi cần chấp nhận một tập version rời rạc hoặc một range, hãy đọc syntax rich version và selector phù hợp. Việc lặp nhiều lần `strictly(...)` trong cùng khối không có nghĩa Gradle tạo một biểu thức OR giữa các giá trị; lệnh sau có thể thay thế ràng buộc trước theo API semantics. Thiết kế một constraint rõ ràng thay vì dùng thứ tự lệnh để mã hóa chính sách mơ hồ.

## 11. Kotlin DSL và Groovy DSL: cùng semantics, khác cú pháp

**Kotlin DSL** (file `build.gradle.kts`):

~~~kotlin
plugins {
    java
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.12.0")

    constraints {
        implementation("org.apache.commons:commons-lang3") {
            version {
                strictly("3.17.0")
            }
            because("Training: selected approved release")
        }
    }
}
~~~

**Groovy DSL** (file `build.gradle`) tương ứng:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.12.0'

    constraints {
        implementation('org.apache.commons:commons-lang3') {
            version {
                strictly '3.17.0'
            }
            because 'Training: selected approved release'
        }
    }
}
~~~

Hai đoạn này không phải hai file trong cùng một demo; chọn **một** DSL phù hợp dự án. Chúng đều mô tả một dependency request và một constraint.

Những điểm dễ nhầm khi chuyển:

- Kotlin dùng dấu ngoặc khi gọi methods, dấu nháy kép và các generic/typed accessors.
- Groovy thường dùng closure, nháy đơn và cú pháp lược dấu ngoặc.
- `strictly` không phải keyword của Kotlin hoặc Groovy; nó là phương thức trong Gradle VersionConstraint DSL.
- `constraints { implementation(...) }` phải nằm trong khối `dependencies` đúng configuration; không thể đặt tùy ý ở `repositories` hoặc `plugins`.

### 11.1. Một rich version trực tiếp trong dependency

Kotlin:

~~~kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3") {
        version {
            prefer("3.17.0")
            reject("3.14.0")
        }
    }
}
~~~

Groovy:

~~~groovy
dependencies {
    implementation('org.apache.commons:commons-lang3') {
        version {
            prefer '3.17.0'
            reject '3.14.0'
        }
    }
}
~~~

Với cách viết này, dependency vẫn **được khai báo trực tiếp** và phiên bản/điều kiện nằm cùng declaration. Với `constraints`, quy tắc tách biệt khỏi dependency request và chỉ có tác dụng khi module tham gia graph.

## 12. Dependency constraints tác động đến transitive dependencies ra sao?

Một lý do quan trọng để dùng constraints là quản lý module được mang vào **gián tiếp**.

Giả sử:

~~~text
:app
   |
   +--> implementation("org.example:framework:2.0")
             |
             +--> transitive dependency "org.example:codec:1.0"

:app constraints
   |
   +--> codec strictly("1.3")
~~~

Nếu `codec` thật sự xuất hiện trong `:app:runtimeClasspath` và constraint từ `implementation` được kế thừa vào classpath đó, Gradle sẽ cố chọn version thỏa strict constraint 1.3. Nếu các dependency requests/rules khác mâu thuẫn, resolution có thể thất bại.

**Điều kiện cần nhớ:** constraint **không thêm** `codec` nếu framework không kéo nó vào graph. Bạn cũng không cần thêm `implementation("codec:...")` chỉ để kiểm soát phiên bản của một transitive dependency.

### 12.1. Scope nào mới áp dụng?

Một số configurations thường thấy trong Java ecosystem:

| Configuration khai báo | Khi nào hợp lý |
| --- | --- |
| `implementation` | Logic ứng dụng hoặc implementation detail của library |
| `api` | Public API của Java library, tác động tới compile API consumer |
| `runtimeOnly` | Dependency/constraint chỉ có ý nghĩa ở runtime, nếu mô hình plugin cho phép |
| `testImplementation` | Test compilation/runtime scopes theo quan hệ cấu hình |
| `annotationProcessor` | Công cụ xử lý annotation khi biên dịch |
| Custom dependency scope | Tooling/code generator hoặc source set riêng |

Configuration được plugin liên kết với resolvable classpath qua các quan hệ thích hợp, nên constraint có thể tác động tới compile/runtime/test theo cách khác nhau. Không giả định `constraints { testImplementation(...) }` quyết định runtime của artifact phát hành.

Ví dụ một module có API công khai dùng class từ Guava, nếu Guava chỉ khai báo `implementation` thì consumer compile API có thể không nhìn thấy type cần thiết. Trường hợp đó nên xem `api` của Java Library plugin, **không phải chỉ tăng độ mạnh của version constraint**.

## 13. Nhiều project, Gradle Module Metadata và publication

Trong multi-project build, bạn có thể áp dụng constraints tại project consumer, hoặc định nghĩa chúng trên project library/platform để các consumer nhận được thông tin phù hợp.

Một điểm rất quan trọng: **dependency constraints không chỉ là đoạn script nội bộ**, chúng có thể được thể hiện trong metadata của component khi publication được cấu hình phù hợp, đặc biệt trong **Gradle Module Metadata**. Nhờ đó, một consumer Gradle khác có thể nhận constraints của producer như một phần dependency metadata.

Nhưng cần phân biệt:

1. **Project dependency trong cùng build:** Gradle dùng mô hình variants/constraints của producer qua metadata của project.
2. **Artifact đã publish với Gradle Module Metadata:** consumer Gradle có thể nhận thông tin versions/variants/constraints chi tiết hơn.
3. **Chỉ có Maven POM:** mô hình Maven dependency scopes không biểu diễn đầy đủ mọi rich version constraint của Gradle. Không giả định consumer Maven cũng nhận toàn bộ semantics `strictly`/`prefer`/`reject`.
4. **Không phải mọi constraint của mọi configuration đều được publish:** còn phụ thuộc outgoing variants/software components và plugin publishing thực tế.

Nếu bạn cung cấp library cho hệ sinh thái đa công cụ (Gradle, Maven, Bazel...), hãy kiểm tra metadata thực sự được publish và hành vi consumer; không dùng strict constraints như một “hợp đồng liên nền tảng” nếu định dạng publish không mang chúng đầy đủ.

### 13.1. Constraint trên producer khác với policy riêng của consumer

Ví dụ project thư viện áp đặt một version vì lý do tương thích public API. Consumer có thể chịu ảnh hưởng khi resolve API/runtime variant. Nhưng policy an ninh của ứng dụng **nên được kiểm soát tại ứng dụng hoặc platform/quy tắc chung**, không tin rằng mọi dependency producer đều khai báo constraints đúng chuẩn và đủ mới.

Một quyết định dùng `strictly` trong thư viện được publish còn có thể gây xung đột với requirements của consumer. Hãy dùng phạm vi nghiêm ngặt có lý do kiểm chứng, không pin bừa chỉ để "ngăn nâng phiên bản".

## 14. So sánh constraints, platforms/BOM, force và locking

Các công cụ này đều có thể liên quan tới version selection nhưng **khác mục đích**.

| Cơ chế | Chức năng | Điểm cần lưu ý |
| --- | --- | --- |
| Dependency constraint | Đặt điều kiện cho version của module khi nó tham gia graph | Không tự thêm module; scope và publication metadata quan trọng |
| Rich version | Diễn đạt require/strictly/prefer/reject trên dependency hoặc constraint | Mạnh/yếu khác nhau; có thể conflict |
| `platform(...)` / Maven BOM | Đưa tập constraints/managed versions theo platform được tiêu thụ | Thường dùng để đồng bộ nhóm thư viện |
| `java-platform` | Tạo project platform mô tả constraints tập trung | Hữu ích khi quản lý nhiều module/project |
| `enforcedPlatform(...)` | Áp các version theo cơ chế enforced mạnh hơn | Có thể ảnh hưởng transitive consumers; không dùng mặc định cho published library |
| `resolutionStrategy.force(...)` | Ép version theo cơ chế resolution strategy | Có thể che xung đột, giảm minh bạch khi debug |
| Dependency locking | Ghi versions đã chọn để tái lập graph qua nhiều lần build | Không tự giải quyết vulnerability hoặc điều kiện metadata sai |
| Dependency verification | Kiểm tra tính toàn vẹn/xác thực artifact theo trust policy | Không tự chọn phiên bản phù hợp |

### 14.1. Một platform constraint không giống một dependency trực tiếp

Ví dụ ứng dụng dùng BOM phổ biến:

~~~kotlin
dependencies {
    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.5"))
}
~~~

Đây là **snippet minh họa**, không phải khuyến nghị một phiên bản Spring Boot mới nhất hay đủ điều kiện bảo mật. Khi BOM có mặt, nó mang thông tin quản lý phiên bản cho những module tương ứng; bản thân nó không tự thêm từng thư viện Spring vào graph. Cần thêm dependencies thực sự.

Không cố thay mọi BOM bằng hàng trăm `strictly(...)` riêng lẻ nếu platform được ecosystem cung cấp và phù hợp. Ngược lại, nếu chỉ cần ngăn một bản dependency nội bộ bị lỗi, một constraint/`reject` có thể rõ ràng hơn việc dựng một platform lớn.

### 14.2. Khi nào dùng java-platform?

Một tổ chức có nhiều project Java có thể tạo một platform dùng chung để quản lý các constraints tương thích:

~~~kotlin
plugins {
    id("java-platform")
}

dependencies {
    constraints {
        api("org.apache.commons:commons-lang3:3.17.0")
    }
}
~~~

Đây là **file `build.gradle.kts` của project platform riêng**, không phải file của application demo. Plugin `java-platform` tạo component variant và các configurations riêng cho việc công bố constraints. Các consumer có thể khai báo `implementation(platform(project(":platform")))` trong cùng multi-project build; tên `:platform` phải thực sự có trong settings và project phải phù hợp.

Có thể dùng rich versions trong các platform constraints theo APIs và chính sách phù hợp. Nhưng không coi platform là biện pháp vượt mọi constraint khác: vẫn có những xung đột cần giải quyết thật.

## 15. Locking và verification: bổ sung, không thay thế rich versions

### 15.1. Version constraints chỉ mô tả điều được chấp nhận

Một range như `strictly("[3.12.0,4.0)")` cho phép nhiều releases. Nếu repository bổ sung bản mới, conflict graph có thể chọn khác theo thời gian. Điều này có thể hợp lệ theo policy nhưng chưa đủ để build tái lập chính xác.

### 15.2. Dependency locking cố định kết quả đã resolve

Gradle cung cấp dependency locking để lưu versions đã chọn cho những configurations cần quản lý. Ví dụ với `build.gradle.kts`:

~~~kotlin
dependencyLocking {
    lockAllConfigurations()
}
~~~

Sau khi đã áp dụng cấu hình này cho project phù hợp, có thể ghi locks khi giải quyết một configuration thật:

~~~bash
./gradlew dependencies --configuration runtimeClasspath --write-locks
~~~

Ví dụ thường tạo/cập nhật lockfile theo cơ chế Gradle, trong các project hiện đại thường là `gradle.lockfile`. Cần commit lockfile theo chính sách dự án và review diff. Để nâng version có kiểm soát, dùng workflow cập nhật locks của Gradle và chạy lại tests; đừng sửa lockfile mù quáng.

**Locking không biến một graph mâu thuẫn thành hợp lệ.** Nếu `strictly`, `reject` và các requests không có ứng viên thỏa, resolution vẫn lỗi. Nếu lock đã chốt một version nay bị reject, phải cập nhật chính sách/version hợp lệ **và** làm mới locks đúng cách.

### 15.3. Dependency verification kiểm tra tính toàn vẹn

Một artifact có version “đúng” vẫn có thể bị phát tán từ repository không đáng tin hoặc bị thay đổi. Gradle dependency verification cho phép quản lý checksums/signatures và metadata tin cậy. Đây là lớp phòng vệ khác với version constraints.

Không chữa checksum mismatch bằng cách tắt verification ngay; kiểm tra repository, artifact và nguồn metadata. Đồng thời, đừng nghĩ `strictly("3.17.0")` tự đảm bảo một file JAR có checksum đúng.

## 16. Debug bằng Gradle reports: từ yêu cầu đến version được chọn

Các lệnh sau áp dụng cho demo mục 5 có plugin `application`:

~~~bash
# Xem dependency graph khi compile
./gradlew dependencies --configuration compileClasspath --console=plain

# Xem dependency graph khi runtime
./gradlew dependencies --configuration runtimeClasspath --console=plain

# Xem lý do commons-lang3 được chọn
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3 --console=plain

# Hỏi thêm thông tin, có thể chứa đường đi/metadata nội bộ
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3 --info --console=plain
~~~

Cách đọc kết quả:

- Tên configuration đúng chưa? Nếu lỗi liên quan runtime, dùng `runtimeClasspath`, không dùng `implementation` trực tiếp.
- Module có thật sự xuất hiện trong graph không? Constraint **không tạo module**.
- Requested version là gì? Selected version là gì?
- Báo cáo có ghi **by constraint**, **by conflict resolution**, **by ancestor**, **by rule** hoặc **forced** tùy ngữ cảnh không?
- Có reason từ `because(...)` hoặc platform không?
- Có version bị reject hoặc strict requirement mâu thuẫn không?
- Graph nào thật sự gắn vào task gặp lỗi?

Báo cáo Gradle có thể hiển thị ký hiệu như `3.12.0 -> 3.17.0` và dấu chú thích cho constraints; cú pháp/độ chi tiết không bất biến giữa các phiên bản Gradle. Dùng report để xác nhận **kết quả và nguyên nhân**, không viết script phụ thuộc vào định dạng log đẹp mắt.

### 16.1. dependencyInsight không phải trình quét lỗ hổng

Nó cho thấy Gradle đã chọn phiên bản nào và vì sao, nhưng **không tự kết luận phiên bản đó an toàn**. Khi quyết định reject một release vì bảo mật, cần tham chiếu CVE/advisory chính thức, ảnh hưởng tới module cụ thể và chính sách của tổ chức.

### 16.2. Dùng đúng configuration khi lỗi nằm trong test hoặc tooling

Nếu lỗi chỉ xuất hiện lúc test, hãy kiểm tra `testRuntimeClasspath` hoặc source-set runtime phù hợp. Nếu lỗi nằm trong plugin classpath/buildscript, việc thêm constraint vào `implementation` của ứng dụng có thể hoàn toàn không tác động tới plugin. Cần tìm đúng **resolution graph** và scope quản lý dependencies của graph đó.

## 17. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Viết constraint nhưng không thấy JAR được tải | Constraint không tự thêm module vào graph | Kiểm tra dependency trực tiếp/transitive thực sự có module |
| Chọn version khác với version ghi trong `implementation("...:x")` | Version declaration thường không phải strict pin | Xem `dependencyInsight`, các requests và constraints |
| `prefer("x")` không được chọn | Có yêu cầu mạnh hơn/platform/range/conflict | Đọc constraints toàn graph; chỉ dùng `strictly` nếu chính sách thật sự bắt buộc |
| `strictly` gây resolution failure | Các strict requirements/ranges không giao nhau | Xác định nguồn conflict và điều chỉnh dependency/constraint |
| `reject` vẫn thấy version cũ trong log | Log có thể hiển thị *requested* version hoặc đang xem khác configuration | Xem **selected version** của đúng configuration, kiểm tra scope |
| Mọi ứng viên đều bị reject | Không còn version hợp lệ | Mở rộng/đổi policy có cơ sở hoặc nâng dependency cung cấp candidates |
| `constraints` trong `testImplementation` không tác động app runtime | Scope khác nhau | Đặt constraint ở scope phù hợp, hoặc platform chung |
| Nhập constraints nhưng plugin vẫn resolve bản lỗi | Plugin classpath khác app classpath | Quản lý plugin/buildscript dependencies ở đúng nơi |
| `strictly` và `force` cho kết quả khó đoán | Có resolution strategy áp đặt version | Kiểm kê rules và ưu tiên mô hình constraints minh bạch |
| Khi publish library consumer không nhận constraint | Metadata chỉ POM hoặc variant không mang constraint | Kiểm tra Gradle Module Metadata và publication |
| Lockfile giữ version cũ sau đổi constraint | Locks chưa được cập nhật có kiểm soát | Dùng workflow update locks rồi review graph/test |
| `Could not find g:m:v` | Phiên bản không tồn tại, repository sai hoặc mạng lỗi | Kiểm tra coordinates/repository trước khi sửa rich version |
| `No matching variant` | Attributes/platform/Java version không tương thích | Debug variant matching, không đổ hết lỗi lên version selector |
| Cấm một version vì “nghe nói có CVE” | Chưa xác minh advisory và affected range | Tra nguồn bảo mật chính thức, ghi lý do vào constraint |
| Bật mọi ràng buộc strictly trong published library | Có thể gây conflict lan sang consumer | Chỉ dùng mức bắt buộc có bằng chứng; xem tác động publication |

### 17.1. Cách giảm phạm vi để tái hiện lỗi

1. Xác định module chính xác theo `group:name` và version được chọn.
2. Tìm trong `dependencies`/`dependencyInsight` của đúng project + configuration.
3. Phân biệt dependency request, constraint, platform và resolution rule.
4. Bỏ qua những module không liên quan thay vì thay mọi dependency cùng lúc.
5. Lập bảng các yêu cầu: require, strictly, prefer, reject và nguồn của từng dòng.
6. Tìm giao của những ràng buộc bắt buộc; kiểm tra có ứng viên trong repositories không.
7. Kiểm tra version cuối cùng và reason sau khi đổi **một** điều kiện.
8. Chạy compile/test/integration tests và review lockfile sau khi hoàn thành.

## 18. Kịch bản xử lý thực tế

### 18.1. Một module transitive có bản lỗi đã xác minh

Nếu một thư viện đưa module `codec` version X vào runtime và advisory chính thức xác định X bị ảnh hưởng, hãy:

1. Xác minh module coordinates và những release bị ảnh hưởng.
2. Tìm phiên bản đã vá có thể dùng, xem compatibility với các consumers.
3. Thêm constraint `reject` cho affected version/range **hoặc** `strictly` vào phạm vi đã xác minh nếu cần chính sách cứng.
4. Chạy `dependencyInsight` để biết selected version và đường transitive.
5. Chạy tests, dependency verification và SBOM/security scan theo quy trình.

**Không khẳng định** reject một bản là đã xử lý toàn bộ vấn đề: có thể dependency khác còn affected, hoặc patch chưa có trong repository.

### 18.2. Dự án nhiều module cần đồng bộ thư viện

Nếu có nhiều modules dùng cùng ecosystem (ví dụ logging, Kotlin, Spring), trước tiên xem BOM/platform phù hợp. `java-platform` có thể giữ constraints tập trung cho Gradle consumers; khi export library, kiểm tra metadata. Từng module vẫn phải khai báo dependency nó thực sự sử dụng.

### 18.3. Thư viện công khai cần cho phép consumer linh hoạt

Một library được phát hành để nhiều ứng dụng sử dụng thường không nên gắn `strictly` vào mọi dependency implementation vì có thể gây conflict. Ưu tiên metadata/constraints có cơ sở, API scope đúng và tập các phiên bản tương thích đã kiểm thử. Chỉ chốt strict version khi việc dùng khác phiên bản thật sự không an toàn/không tương thích.

### 18.4. Ứng dụng cần build tái lập

Ứng dụng cuối thường cần graph ổn định qua CI và deployment. Dùng constraints/rich versions để mô tả **chính sách hợp lệ**; dùng dependency locking để lưu **kết quả cụ thể**; dùng verification để bảo vệ **artifact bytes**; dùng tests để bảo đảm **hành vi**. Bốn tầng này bổ sung nhau.

## 19. Bài tập tự kiểm tra

**Bài A — Khái niệm.** Một build chỉ có `constraints { implementation("g:a") { version { strictly("2.0") } } }`, không có dependency nào dẫn tới `g:a`. Gradle có tải `a` không?  
**Đáp án:** không, constraint không tự thêm module.

**Bài B — Mức yêu cầu.** `implementation("g:a:1.0")` và một đường khác yêu cầu 1.5. Version 1.0 có chắc được chọn không?  
**Đáp án:** không. Version string thông thường không phải pin nghiêm ngặt; cần xem conflict resolution và các constraints liên quan.

**Bài C — Strict conflict.** Graph có hai `strictly("1.5")` và `strictly("1.8")` cho cùng module. Chọn bản cao hơn được không?  
**Đáp án:** trong resolution thông thường không có version cố định thỏa cả hai; phải giải quyết mâu thuẫn hoặc build fail.

**Bài D — Prefer.** Một consumer có `prefer("1.5")` nhưng dependency khác yêu cầu 1.8. Có bảo đảm 1.5 không?  
**Đáp án:** không. `prefer` là ưu tiên mềm, không vượt các yêu cầu mạnh hơn.

**Bài E — Reject.** `reject("1.6")` nhưng repository chỉ có version 1.6 đúng với mọi yêu cầu còn lại. Gradle có tự tìm 1.5 ở đâu đó không?  
**Đáp án:** không; nếu không có candidate hợp lệ, resolution fail.

**Bài F — Range.** `strictly("[1.4,2.0)")` có cho phép 2.0 không?  
**Đáp án:** không. Ký hiệu ngoặc tròn phải loại trừ mốc trên.

**Bài G — Rich combination.** `strictly("[1.4,2.0)")` + `prefer("1.7")` + `reject("1.6")` nghĩa gì?  
**Đáp án:** chỉ chấp nhận phiên bản trong range, ưu tiên 1.7, loại 1.6; kết quả còn phụ thuộc yêu cầu khác.

**Bài H — Vì sao.** `because("...")` có tự chọn version không?  
**Đáp án:** không. Nó mô tả lý do và hỗ trợ báo cáo, không thay thế `strictly`/`reject`.

**Bài I — Scope.** Constraint nằm ở `testImplementation` có tự chặn version khi chạy ứng dụng production không?  
**Đáp án:** không mặc định; phải kiểm tra scope của graph production và đặt constraint ở đó nếu cần.

**Bài J — Tooling.** Lệnh nào xem vì sao `commons-lang3` chọn 3.17.0 trên runtimeClasspath?  
**Đáp án:** `./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3`.

**Bài K — Platform.** Import một Maven BOM có tự thêm mọi thư viện được BOM quản lý không?  
**Đáp án:** không, BOM mang version management/constraints; cần dependencies thực tế.

**Bài L — Locking.** `strictly("[1.0,2.0)")` có bảo đảm mọi ngày đều resolve ra cùng một bản không?  
**Đáp án:** không nhất thiết, vì có nhiều releases hợp lệ; cần locking và quản lý repository/metadata phù hợp để tái lập.

**Bài M — Verification.** Chọn phiên bản đã được phê duyệt có chứng minh JAR download không bị thay đổi không?  
**Đáp án:** không; cần dependency verification, checksums/signatures và repository trust.

**Bài N — Publication.** Publish library với Gradle Module Metadata có giống publish chỉ Maven POM về rich versions không?  
**Đáp án:** không. Module Metadata có thể mang constraints/variant information chi tiết hơn, Maven POM có mô hình hạn chế.

**Bài O — Kết quả demo.** Với `strictly("3.17.0")` và declaration `commons-lang3:3.12.0`, hãy chạy báo cáo. Kết quả muốn chứng minh là gì?  
**Đáp án:** Gradle chọn 3.17.0 (nếu resolution thành công và không có rules mâu thuẫn), đồng thời main Java in `Gradle constraints`.

## 20. Checklist trước khi áp dụng rich versions trong dự án

- [ ] Đã xác định **module thật sự tham gia graph** chưa, hay chỉ thêm constraint?
- [ ] Biết module/version được yêu cầu từ đâu: direct, transitive, platform, plugin hay rule?
- [ ] Đã chọn đúng scope configuration: implementation/api/test/runtime/tooling?
- [ ] Ý định là **pin nghiêm ngặt**, **gợi ý ưu tiên**, **range bắt buộc**, hay **từ chối phiên bản cụ thể**?
- [ ] Có ràng buộc `strictly` nào mâu thuẫn với constraint khác không?
- [ ] `reject` có dựa trên lý do đã xác minh, không phải suy đoán bảo mật?
- [ ] `because(...)` mô tả được lý do để người khác hiểu policy không?
- [ ] Đã kiểm tra **selected version** của đúng configuration qua `dependencyInsight` chưa?
- [ ] Với thư viện publish, đã xem Gradle Module Metadata/consumers bị ảnh hưởng chưa?
- [ ] Có cân nhắc BOM/platform nếu quản lý cả họ dependencies không?
- [ ] Có tránh `force` chỉ để che các conflict chưa được hiểu không?
- [ ] Với build cần tái lập, đã dùng dependency locking và review lockfile chưa?
- [ ] Với bảo vệ artifact, có quy trình dependency verification và repository trust riêng chưa?
- [ ] Đã chạy tests phù hợp khi thay phiên bản dependency chưa?
- [ ] Đã tránh hardcode credentials hoặc in metadata nhạy cảm khi debug chưa?

## 21. Tài liệu tham khảo chính thức

- [Gradle — Declaring Dependency Constraints](https://docs.gradle.org/current/userguide/dependency_constraints.html): cú pháp constraints và ý nghĩa dependency constraint.
- [Gradle — Declaring Rich Versions](https://docs.gradle.org/current/userguide/rich_versions.html): `require`, `strictly`, `prefer`, `reject` và ranges.
- [Gradle — Dependency Resolution](https://docs.gradle.org/current/userguide/dependency_resolution.html): graph resolution, conflict resolution và selection.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`, resolution reasons.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): quản lý tọa độ/versions dùng trong build, không tự áp version constraints cho graph chỉ bằng catalog.
- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): Maven BOM, `java-platform`, dependency alignment.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): tái lập graph bằng lock state.
- [Gradle — Verifying Dependencies](https://docs.gradle.org/current/userguide/dependency_verification.html): integrity/trust của artifact.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): scopes API/implementation và publication.
- [Gradle — Gradle Module Metadata](https://docs.gradle.org/current/userguide/publishing_gradle_module_metadata.html): biểu diễn variants và constraints cho consumers.
- [Gradle Kotlin DSL API](https://docs.gradle.org/current/kotlin-dsl/): signature các methods trong `VersionConstraint` và `DependencyConstraint`.

**Ghi nhớ:** dependency constraint **không tự thêm** module; nó điều chỉnh cách chọn version khi module có mặt. `strictly` giới hạn cứng phiên bản/range, `prefer` gợi ý mềm, `reject` loại ứng viên, còn `require` mô tả yêu cầu có thể được hòa giải. Kiểm tra lựa chọn thực tế bằng `dependencyInsight`, và dùng platform, locking, verification cho các mục tiêu khác nhau thay vì ép một công cụ giải quyết mọi vấn đề.