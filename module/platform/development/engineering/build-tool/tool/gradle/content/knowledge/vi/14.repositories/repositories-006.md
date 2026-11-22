# Lọc nội dung kho bằng `content filter` và `exclusiveContent` trong Gradle

## 1. Vấn đề cần giải quyết

Một ứng dụng JVM có thể dùng thư viện công khai từ Maven Central, thư viện nội bộ từ Maven repository của công ty, snapshot từ một kho thử nghiệm và plugin Gradle từ plugin portal. Nếu chỉ viết nhiều dòng `maven { url = ... }`, bạn đang giao cho Gradle quyền tìm **nhiều tọa độ dependency ở nhiều kho** theo quy tắc resolution. Điều này dẫn đến ba vấn đề:

- **Hiệu năng:** truy vấn những kho mà chắc chắn không chứa module cần tìm.
- **Độ tin cậy:** repository A và B chứa cùng `group:name:version` nhưng metadata/artifact khác nhau, hoặc repository đáng tin tạm thời không đáp ứng.
- **An toàn chuỗi cung ứng:** tên thư viện nội bộ bị gửi đến kho công khai; nếu một package cùng tên được xuất bản ở nơi không đáng tin, việc chọn nguồn sai có thể trở thành dependency confusion.

Gradle có hai cơ chế quan trọng:

1. `content { ... }`: lọc **những tọa độ một repository riêng lẻ được phép cung cấp**. Bạn phải tự đặt filter ở các repository có liên quan.
2. `exclusiveContent { forRepository { ... }; filter { ... } }`: khẳng định **các tọa độ khớp filter chỉ được tìm trong repository được chỉ định**, và những repository khác tự bị loại khỏi khả năng cung cấp chúng.

**Thông điệp cốt lõi:** `content` là ràng buộc cục bộ trên từng kho; `exclusiveContent` là quan hệ độc quyền giữa **tọa độ module** và **một hoặc một nhóm kho**. Hai cơ chế ảnh hưởng **nơi Gradle được tìm dependency**, không tự xác thực chữ ký artifact, không thay thế HTTPS/credentials và không quyết định nơi publish.

Sau bài này bạn sẽ:
- Viết được `includeGroup`, `excludeGroup`, `includeModule`, `includeGroupByRegex` cùng các biến thể liên quan.
- Phân biệt group chính xác với group kèm subgroups.
- Dự đoán repo nào được tìm khi có nhiều filter và repository order.
- Viết cấu hình `exclusiveContent` đúng Groovy DSL.
- Chọn nơi khai báo ở `build.gradle` hay `settings.gradle`, tách project dependencies khỏi plugin resolution.
- Hiểu repository stickiness, transitive dependencies, snapshot/release repository filtering.
- Thiết kế ví dụ offline/online kiểm chứng, chẩn đoán lỗi thiếu module và giới hạn bảo mật.

**Môi trường:** Gradle **Groovy DSL** (`build.gradle` và `settings.gradle`). Ví dụ Java minh họa dùng Java 17+. Trên Linux/macOS chạy `./gradlew`; Windows PowerShell dùng `.\gradlew.bat`. Phần API `includeGroupAndSubgroups` đòi hỏi Gradle hỗ trợ tính năng này (được giới thiệu từ Gradle 8.1); trên bản cũ phải dùng include chính xác hoặc regex phù hợp.

## 2. Repository resolution khác dependency declaration

Một dependency Maven thông thường có dạng:

~~~text
group : name : version
org.apache.commons : commons-lang3 : 3.17.0
com.acme.platform : auth-client : 1.4.0
~~~

Khi bạn khai:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}
~~~

bạn chỉ nói **cần module nào**. Repository quyết định Gradle **được tìm module đó ở đâu**. Chẳng hạn:

~~~groovy
repositories {
    mavenCentral()
    maven {
        url = uri('https://repo.company.example/maven/releases')
    }
}
~~~

Với cấu hình có nhiều repository, thứ tự khai báo có ý nghĩa: Gradle tìm metadata/module theo các repository được phép và khi đã xác định nguồn cho một module, nó thường cố tải các artifact của module từ **cùng nguồn đã chọn** (repository stickiness). Không nên suy diễn rằng Gradle sẽ vô điều kiện tải JAR từ kho B chỉ vì kho A có metadata nhưng thiếu artifact.

**URL `repo.company.example` trên đây là ví dụ hình thức**; nếu chưa thay bằng repository có thật, build sẽ không tải được dependency nội bộ. Những bài thực hành chạy thật ở phần 7 dùng Maven Central và một module công khai.

### 2.1. Filter tác động lên *tọa độ*, không lên file đang tải

| Câu hỏi | Thành phần chịu trách nhiệm |
| --- | --- |
| Module nào được yêu cầu? | `dependencies { ... }`, constraints, platform, plugins |
| Repo nào được phép chứa module? | `repositories { ... content { ... } }` và `exclusiveContent` |
| Version nào được chọn? | Dependency resolution, constraints, conflict resolution, locking... |
| Artifact có đúng nguồn/nội dung đáng tin? | Repository trust, HTTPS, dependency verification, checksums/signatures khi cấu hình |
| Nơi publish artifact lên? | `publishing { repositories { ... } }`, tách khỏi filter của dependency resolution |

Đừng hiểu `includeGroup` là cơ chế **copy/upload** artifact đến repository. Nó chỉ hướng dẫn quá trình **đọc/tìm dependency**.

## 3. `content { }`: cho phép và từ chối trên từng repository

Repository content filtering dùng block `content` bên trong repository definition:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/maven/releases')
        content {
            includeGroup 'com.acme.platform'
        }
    }
    mavenCentral {
        content {
            excludeGroup 'com.acme.platform'
        }
    }
}
~~~

Diễn giải:
- Kho nội bộ **chỉ** được tìm cho group `com.acme.platform`.
- Maven Central được tìm cho mọi group **trừ** `com.acme.platform`.
- Quy tắc exclude ở Maven Central là quyết định bạn khai báo **riêng**; nó không tự phát sinh từ `includeGroup` của kho nội bộ.
- Vì thế có thể bảo vệ nhóm nội bộ khỏi bị gửi tới Maven Central **nếu bạn khai đầy đủ các filter ở tất cả kho khác**. Nhưng việc bảo trì thủ công sẽ khó khi số repository tăng.

### 3.1. Ngữ nghĩa include/exclude

Mặc định một repository không có content filter sẽ nhận mọi tọa độ có thể hỗ trợ:

1. Nếu **chỉ include**, repo chỉ được phép cung cấp những gì khớp include; các module còn lại bị loại ngầm.
2. Nếu **chỉ exclude**, repo có thể cung cấp mọi thứ trừ những gì bị exclude.
3. Nếu có **cả include và exclude**, module phải **khớp ít nhất một include** và **không khớp exclude**.

Ví dụ:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/maven')
        content {
            includeGroupByRegex 'com\\.acme\\..*'
            excludeModule 'com.acme.legacy', 'old-api'
        }
    }
}
~~~

Repo được phép chứa các group khớp pattern `com\.acme\..*`, nhưng module `com.acme.legacy:old-api` bị loại. Đây là phép lọc trên **group/module của dependency**, không lọc tên file JAR. Lưu ý Groovy string chứa regex phải được escape đúng: trong single-quoted Groovy source `'com\\.acme\\..*'` truyền các dấu `\` cần thiết cho regex.

**Không suy ra** rằng một repository có `includeGroup 'com.acme.platform'` sẽ tự được hỏi khi Gradle resolve `com.acme.platform.auth:client`. `includeGroup` khớp **chính xác** tên group; hãy dùng `includeGroupAndSubgroups` (trên Gradle hỗ trợ) hoặc regex được kiểm chứng nếu muốn nhiều subgroup.

### 3.2. Các API lọc thường gặp

| API Groovy DSL | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `includeGroup 'g'` | Chỉ định **một group** chính xác | `includeGroup 'org.apache.commons'` |
| `excludeGroup 'g'` | Loại một group chính xác | `excludeGroup 'com.acme.internal'` |
| `includeGroupByRegex 'regex'` | Bao gồm group khớp biểu thức chính quy | `includeGroupByRegex 'com\\.acme\\..*'` |
| `excludeGroupByRegex 'regex'` | Loại group theo regex | `excludeGroupByRegex 'com\\.acme.*'` |
| `includeGroupAndSubgroups 'g'` | Bao gồm group và những group có tiền tố `g.` | `includeGroupAndSubgroups 'com.acme'` |
| `excludeGroupAndSubgroups 'g'` | Loại group và những group con tương ứng | `excludeGroupAndSubgroups 'com.acme'` |
| `includeModule 'g', 'name'` | Chỉ định một module `group:name` | `includeModule 'org.slf4j', 'slf4j-api'` |
| `excludeModule 'g', 'name'` | Loại module `group:name` cụ thể | `excludeModule 'com.acme', 'legacy'` |

Gradle còn hỗ trợ các filter chi tiết khác (version, configuration, attributes) ở API `RepositoryContentDescriptor`. Không nên tự chế điều kiện lọc metadata bên ngoài hợp đồng API hoặc dùng regex quá rộng khi tọa độ có thể liệt kê cụ thể.

**Về group con:** `includeGroupAndSubgroups 'com.acme'` khớp `com.acme` và `com.acme.foo`, nhưng không nên khớp `com.acmefoo`. Khi hỗ trợ Gradle cũ không có method này, regex tương đương về ý nghĩa thường là `com\\.acme(\\..*)?`; kiểm tra riêng cú pháp regex/Groovy escaping và phiên bản đang chạy.

### 3.3. Lọc theo module thay vì toàn group

Giả sử một nhóm `org.acme` có hầu hết thư viện công khai nhưng duy nhất `org.acme:billing-core` phải lấy từ kho nội bộ:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/maven')
        content {
            includeModule 'org.acme', 'billing-core'
        }
    }
    mavenCentral()
}
~~~

Đoạn này **không đủ để đảm bảo độc quyền** vì Maven Central chưa bị exclude module đó. Muốn giới hạn chắc chắn nguồn cung cấp cho một module, nên dùng `exclusiveContent` như phần 4.

### 3.4. Lọc version có thể cần thiết nhưng phải hiểu ngữ nghĩa

Gradle có các thao tác lọc chi tiết theo version trong repository content descriptor, gồm cơ chế version hoặc version pattern theo API và phiên bản hỗ trợ. Đừng nhầm **lọc repository theo version** với **version selection** hoặc dependency constraints. Nếu tổ chức muốn release và snapshot đi hai kho Maven riêng, thường nên dùng API `mavenContent` chuyên biệt (`releasesOnly`, `snapshotsOnly`) thay vì tự regex mọi chuỗi `-SNAPSHOT`.

## 4. `exclusiveContent { }`: ràng buộc nguồn độc quyền

Đây là điểm khác biệt chính giữa hai công cụ.

### 4.1. Tại sao content filter thông thường chưa đủ?

Ví dụ:

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/maven')
        content {
            includeGroup 'com.acme.internal'
        }
    }
    mavenCentral()
}
~~~

Repo nội bộ được phép chứa `com.acme.internal`, **nhưng Maven Central không bị cấm** tìm group này. Nếu cần bảo đảm `com.acme.internal:secret-api` chỉ được tìm từ nguồn nội bộ, phải exclude group ở tất cả repo khác; thêm repo mới sau này có thể phá quy tắc.

`exclusiveContent` biểu diễn chính sách ở **một chỗ**: group đó chỉ được tìm trong kho được chỉ định; Gradle tự thiết lập loại trừ tương ứng trên các kho khác.

### 4.2. Cú pháp Groovy DSL được khuyên dùng

~~~groovy
repositories {
    mavenCentral()

    exclusiveContent {
        forRepository {
            maven {
                name = 'companyInternal'
                url = uri('https://repo.company.example/maven')
            }
        }
        filter {
            includeGroupAndSubgroups 'com.acme'
        }
    }
}
~~~

Giải thích chính xác:
- `forRepository { maven { ... } }` khai báo kho (hoặc nhà máy tạo kho) độc quyền cho nhóm tọa độ xác định.
- `filter { includeGroupAndSubgroups 'com.acme' }` nói `com.acme` và mọi subgroup `com.acme.*` **chỉ** được tìm trong kho đó.
- Maven Central được đặt trước trong đoạn trên **vẫn sẽ không được truy vấn** cho các tọa độ khớp `com.acme`, vì exclusiveContent mạnh hơn thứ tự repository.
- Kho nội bộ **không** được tìm các module bên ngoài tập exclusive đó, trừ khi bạn cấu hình cấu trúc khác phù hợp.
- Nếu một module `com.acme.foo:bar:1.0` **không tồn tại** trong kho được cho phép, Gradle **không fallback** sang Maven Central để tìm module đó. Đây là hành vi mong muốn của chính sách độc quyền, không phải lỗi để “sửa” bằng cách bỏ filter.

Ví dụ URL trên là giả định, dùng cho **hệ thống có kho thật**. Không chạy nguyên đoạn rồi kỳ vọng truy cập thành công vào `repo.company.example`.

### 4.3. Quy tắc API trong `exclusiveContent`

- `filter` của exclusive content chỉ nhận **inclusive filters** như `includeGroup`, `includeGroupAndSubgroups`, `includeModule`, regex tương ứng. Không đặt `excludeGroup` trong `filter` của exclusive content.
- `forRepository` dành cho một kho; API cũng có `forRepositories` nếu nhiều kho đáng tin cùng được phép chứa tập tọa độ.
- **Exclusive không có nghĩa chỉ một repository duy nhất cho toàn bộ build.** Một tập module được đánh dấu exclusive có thể có một hoặc nhiều kho được chỉ định; các module ngoài tập đó vẫn do những repo phù hợp khác cung cấp.
- **Không coi exclusion là metadata của artifact.** Nó là chính sách resolution của build đang chạy.

### 4.4. Độc quyền theo một module

Nếu chỉ riêng module `com.acme:license-client` buộc đi qua kho nội bộ:

~~~groovy
repositories {
    mavenCentral()
    exclusiveContent {
        forRepository {
            maven {
                url = uri('https://repo.company.example/maven/licenses')
            }
        }
        filter {
            includeModule 'com.acme', 'license-client'
        }
    }
}
~~~

Khi đó các module khác trong group `com.acme` **không tự bị độc quyền**. Nếu ý định là bảo vệ toàn bộ package family nội bộ, dùng group/subgroup thay vì filter một module.

### 4.5. Một tập module có nhiều kho được phép

Trong trường hợp tổ chức **thật sự có hai kho** cùng được coi là nguồn độc quyền, bạn có thể khai đối tượng repository rồi đưa vào `forRepositories`:

~~~groovy
repositories {
    def internalReleaseRepo = maven {
        name = 'internalReleases'
        url = uri('https://repo.company.example/maven/releases')
    }
    def internalSnapshotRepo = maven {
        name = 'internalSnapshots'
        url = uri('https://repo.company.example/maven/snapshots')
    }

    exclusiveContent {
        forRepositories internalReleaseRepo, internalSnapshotRepo
        filter {
            includeGroupAndSubgroups 'com.acme'
        }
    }

    mavenCentral()
}
~~~

Ý nghĩa: các module group nội bộ chỉ được tìm trong **hai** kho chỉ định, không tìm ở Maven Central. Bên trong tập hai kho, thứ tự và khả năng cung cấp của từng kho vẫn quan trọng. **Đây là ví dụ cấu hình tham khảo**, yêu cầu URL/thông tin xác thực có thật; nếu muốn release/snapshot tách rõ, bổ sung `mavenContent` tương ứng như phần 6.

## 5. So sánh `content` và `exclusiveContent`

| Tình huống | `content {}` | `exclusiveContent {}` |
| --- | --- | --- |
| Giới hạn kho A chỉ được hỏi về group nội bộ | Có | Có |
| Tự động loại cùng group khỏi mọi repository khác | **Không** | **Có** |
| Cho phép fallback sang kho B nếu B cũng nhận group | Có thể, theo bộ lọc và resolution | **Không**, nếu B không thuộc các kho được chỉ định là exclusive |
| Quản lý tập include/exclude riêng cho từng kho | Có | `filter` chỉ chứa include, exclusion sang kho khác là ngầm định |
| Giảm truy vấn thừa | Có | Có |
| Hạn chế lộ tọa độ nội bộ ra kho công khai | Chỉ khi cấu hình đủ exclusions ở mọi kho | Thể hiện chính sách này trực tiếp |
| Tốt cho kho chỉ có artifact của một nhóm nhỏ | Có | Có, nhất là nếu artifact phải xuất phát duy nhất từ kho đó |
| Phù hợp khi dependency được phép xuất hiện ở nhiều nguồn tùy availability | Có thể | Không, trừ khi mọi nguồn cho phép đều được khai trong exclusive set |
| Hành vi khi kho độc quyền thiếu module | Repo khác không bị cấm nếu filter cho phép | Không tìm ở repo không thuộc exclusive set; resolution thất bại nếu tập exclusive không có |

**Gợi ý quyết định:** Dùng `content` để mô tả phạm vi của từng kho. Dùng `exclusiveContent` khi yêu cầu thực sự là “tọa độ X tuyệt đối chỉ được resolve từ tập kho Y”. Với thư viện nội bộ có nguy cơ dependency confusion, ưu tiên chính sách exclusive trên nguồn tin cậy.

## 6. Dependency bắc cầu: filter không được áp theo kiểu “cha kéo theo con”

Một module có thể phụ thuộc vào nhiều module khác:

~~~text
com.acme:internal-service:1.0
  ├── com.acme:internal-model:1.0
  ├── org.slf4j:slf4j-api:2.x
  └── org.apache.commons:commons-lang3:3.x
~~~

Giả sử `com.acme` chỉ được tìm ở kho nội bộ qua `exclusiveContent`:

- Module `com.acme:internal-service` và `com.acme:internal-model` được tìm **trong kho nội bộ**, không ở Maven Central.
- `org.slf4j:slf4j-api` và `org.apache.commons:commons-lang3` là **các tọa độ khác**, nên được tìm ở repository cho phép chúng, ví dụ Maven Central.
- **Không có quy tắc** “dependency bắc cầu của module nội bộ phải nằm trong cùng kho nội bộ”.
- Nếu kho nội bộ chứa một dependency bắc cầu thuộc group khác nhưng kho chỉ cho phép `com.acme`, Gradle sẽ **không tìm** dependency ấy tại đó. Bạn phải khai source phù hợp cho từng group hoặc xác định rõ tập exclusive khác.

Ví dụ không an toàn về mặt mô hình:

~~~groovy
repositories {
    exclusiveContent {
        forRepository {
            maven {
                url = uri('https://repo.company.example/maven')
            }
        }
        filter {
            includeGroupAndSubgroups 'com.acme'
        }
    }
    // Không có Maven Central hoặc kho nào cho SLF4J/Commons!
}
~~~

Nếu POM của module nội bộ cần `org.slf4j`, dependency resolution có thể thất bại dù module chính có sẵn. Đừng “sửa” bằng cách bỏ độc quyền nhóm nội bộ; **bổ sung kho phù hợp** cho các module khác:

~~~groovy
repositories {
    exclusiveContent {
        forRepository {
            maven {
                url = uri('https://repo.company.example/maven')
            }
        }
        filter {
            includeGroupAndSubgroups 'com.acme'
        }
    }
    mavenCentral()
}
~~~

Tùy chính sách công ty, tổ chức có thể dùng **mirror nội bộ** cho cả dependencies công khai thay vì hỏi Maven Central trực tiếp. Hãy xác định mô hình trust và routing trước khi viết script.

## 7. Phòng thực hành chạy được: `exclusiveContent` với Maven Central

Để kiểm chứng mà **không cần một kho riêng giả định**, bài này dùng một dependency công khai thật từ Maven Central. Chúng ta đặt `mavenLocal()` trước trong danh sách, sau đó chỉ định group `org.apache.commons` **độc quyền cho Maven Central**. Mục tiêu: quan sát nguyên tắc “exclusive thắng repository order”.

### 7.1. Điều kiện và cấu trúc

- Có Gradle Wrapper của bản Gradle hỗ trợ `exclusiveContent` (API xuất hiện từ Gradle 6.2; nên dùng Wrapper phiên bản hiện đại tương thích Java 17).
- Có JDK 17 cho Java toolchain (hoặc toolchain provisioning đã cấu hình).
- Có mạng để tải dependency từ Maven Central nếu chưa có trong cache.
- Bài học không cần kho công ty, token hoặc private artifact.

~~~text
repository-filter-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/main/java/demo/Main.java
~~~

Nếu chưa có Wrapper, dùng Gradle đã cài để chạy `gradle wrapper` một lần, sau đó đưa bộ Wrapper vào VCS.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'repository-filter-lab'
~~~

**`build.gradle` — nguyên file:**

~~~groovy
plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    // Khai trước để làm rõ rằng thứ tự không thắng exclusive rule.
    // Trong production, thường tránh mavenLocal để tăng tính tái lập.
    mavenLocal()

    exclusiveContent {
        forRepository {
            mavenCentral()
        }
        filter {
            includeGroup 'org.apache.commons'
        }
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
}

application {
    mainClass = 'demo.Main'
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
        String word = StringUtils.capitalize("gradle");
        System.out.println("Xin chào " + word);
    }
}
~~~

Đoạn Java là chương trình Java 17 đầy đủ: package trùng thư mục, class public trùng tên file, import library được khai ở `implementation`. Phiên bản `commons-lang3:3.17.0` ở đây là phiên bản ví dụ cố định, **không phải lời khẳng định phiên bản mới nhất**.

### 7.2. Chạy và xem kết quả

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --configuration runtimeClasspath --dependency commons-lang3
./gradlew run --quiet
~~~

**Stdout chính xác của chương trình Java (ngoài log Gradle):**

~~~text
Xin chào Gradle
~~~

Tại sao bài thực hành có ý nghĩa?
1. `mavenLocal()` được khai trước `mavenCentral()`.
2. Nhưng `exclusiveContent` nói group `org.apache.commons` chỉ được phép tìm từ repository được tạo bởi `mavenCentral()` trong `forRepository`.
3. Vì vậy, với dependency `org.apache.commons:commons-lang3:3.17.0`, Gradle không được hỏi `mavenLocal` cho module group này.
4. Những module không thuộc group đó vẫn có thể được xử lý bởi các repository khác phù hợp trong cấu hình. Ví dụ ngắn này không thêm chúng để giữ quy tắc dễ quan sát.
5. `dependencyInsight` giúp xem version và lý do được chọn; nó **không phải** một báo cáo nguồn download chi tiết trong mọi phiên bản Gradle. Nếu cần kiểm chứng request, dùng log `--info`/`--debug` trong môi trường thử nghiệm không chứa credentials.

**Không dùng `mavenLocal()` như khuyến nghị production**: local repository thay đổi theo máy, có thể gây mất tính tái lập. Nó chỉ là **đối chứng** cho quy tắc độc quyền trong bài học.

### 7.3. Chuyển sang `content` thông thường để so sánh

Trong **bản sao dự án thực hành**, thay riêng block `repositories` bằng:

~~~groovy
repositories {
    mavenLocal()

    mavenCentral {
        content {
            includeGroup 'org.apache.commons'
        }
    }
}
~~~

Trong trường hợp này, Maven Central chỉ cung cấp `org.apache.commons`; **mavenLocal không hề bị exclude** group đó. Vì `mavenLocal` được khai trước, một bản sao `commons-lang3` có metadata phù hợp trong local repo có thể được xem xét theo quy tắc repository order, và bạn không còn chính sách “Maven Central là nguồn duy nhất” nữa. Đoạn này **không tương đương** block `exclusiveContent` ban đầu.

Để content filters bình thường mô tả ranh giới tương tự, phải thêm exclusion **ở kho local**:

~~~groovy
repositories {
    mavenLocal {
        content {
            excludeGroup 'org.apache.commons'
        }
    }
    mavenCentral {
        content {
            includeGroup 'org.apache.commons'
        }
    }
}
~~~

Lúc này hai repo được lọc thủ công. Nhưng nếu sau đó thêm một repository thứ ba không có exclusion, chính sách có thể lại bị phá. `exclusiveContent` thể hiện ràng buộc khó quên hơn.

### 7.4. Một bài kiểm chứng bổ sung

Thay dependency trong dự án thành một group **không** được `mavenCentral` cho phép trong cấu hình content-filter thứ hai, ví dụ một module trong group `com.google.guava`. Lúc đó, Gradle chỉ có thể tìm nó tại các repository khác được phép, hoặc thất bại nếu không có repository phù hợp. Đây không phải lỗi của tên module: chính **repository filter** đã quyết định tập nguồn được hỏi.

Với `exclusiveContent`, nếu bạn thêm một module nằm ngoài group exclusive, nó không tự được tìm ở Maven Central vì Maven Central trong block exclusive đang là repository dành riêng cho group đó; muốn module công khai khác, hãy bổ sung **repository phù hợp** vào thiết kế (ví dụ một public repository khác hoặc mirror nội bộ), không xóa bỏ filter vì “build lỗi”.

## 8. Đặt filter ở `settings.gradle`: quản lý tập trung cho multi-project

Đối với build nhiều project, nếu mỗi `app/build.gradle`, `core/build.gradle` tự khai repository, dễ xảy ra tình huống project A có chính sách đúng còn project B quên exclude group nội bộ.

Gradle cho phép quản lý repository resolution tập trung trong **`settings.gradle`**:

~~~groovy
import org.gradle.api.initialization.resolve.RepositoriesMode

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)

    repositories {
        mavenCentral()

        exclusiveContent {
            forRepository {
                maven {
                    name = 'internal'
                    url = uri('https://repo.company.example/maven')
                }
            }
            filter {
                includeGroupAndSubgroups 'com.acme'
            }
        }
    }
}

rootProject.name = 'enterprise-build'
include 'core', 'app'
~~~

**Đây là cấu hình mẫu cần thay bằng kho nội bộ thực và policy credentials phù hợp**, không phải project có thể tải private artifact từ URL giả định.

Giải thích:
- `dependencyResolutionManagement` quản lý **project dependency repositories** cho các subprojects.
- `repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)` từ chối khi project cố thêm repository riêng trong `build.gradle`; nhờ đó chính sách tập trung không bị tùy ý thay đổi.
- Maven Central chỉ cung cấp modules không thuộc tập `com.acme` exclusive; nhóm nội bộ chỉ được tìm ở kho nội bộ chỉ định.
- Nếu project ở một subproject vẫn khai `repositories { mavenCentral() }`, build có thể báo lỗi vì repositories mode chứ không phải vì thiếu Maven Central.
- Centralizing repositories giúp review/audit thuận tiện, nhưng không tự đảm bảo artifact trusted. Kết hợp với dependency verification, locking và kiểm soát credentials theo chính sách bảo mật.

### 8.1. Phân biệt scopes: `repositories` ở đâu?

| Vị trí | Mục đích | Filter tác động vào |
| --- | --- | --- |
| `build.gradle -> repositories` | Tìm dependencies của project này | Module được resolve qua configurations của project |
| `settings.gradle -> dependencyResolutionManagement.repositories` | Chính sách repository project deps của toàn build | Dependency resolution của project theo repositories mode |
| `settings.gradle -> pluginManagement.repositories` | Tìm Gradle plugins | Plugin marker/implementation modules trong cơ chế plugin resolution |
| `build.gradle -> buildscript.repositories` | Tìm dependencies cho **buildscript classpath** theo đường truyền thống | Buildscript dependencies, không phải `implementation`/`testImplementation` |
| `publishing.repositories` | Nơi upload artifact do dự án tạo | **Publishing destination**, không phải các filter tải dependency ở trên |

Bạn có thể cấu hình hai tập repository khác nhau đều có tên `repositories` nhưng không thể mặc định coi một filter tại `dependencyResolutionManagement` là filter của `pluginManagement` hoặc ngược lại.

## 9. `pluginManagement` và trường hợp khó với `exclusiveContent`

Plugin resolution là một bài toán riêng vì Gradle dùng plugin IDs và plugin marker artifacts. Một plugin:

~~~groovy
plugins {
    id 'com.acme.gradle.rules' version '1.2.0'
}
~~~

có thể cần plugin marker module và implementation module từ những group khác nhau. Nếu dùng `exclusiveContent` trong plugin repositories mà chỉ include group của implementation, plugin marker có thể không được tìm ở nguồn mong muốn.

Ví dụ cấu hình **mang tính minh họa** ở `settings.gradle`:

~~~groovy
pluginManagement {
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    url = uri('https://repo.company.example/gradle-plugins')
                }
            }
            filter {
                includeGroupAndSubgroups 'com.acme.gradle'
            }
        }
        gradlePluginPortal()
    }
}
~~~

Hai điều cần kiểm tra:
1. Plugin ID, marker coordinates và implementation artifact group có thực sự nằm trong tập included hay không.
2. Plugin implementation có dependency bắc cầu ở group khác và cần một repository phù hợp không.

**Cảnh báo chính thức quan trọng:** Nếu cấu hình `exclusiveContent` trong `pluginManagement` của `settings.gradle`, Gradle có ràng buộc khiến việc thêm repository ở `buildscript.repositories` của project trở thành **không hợp lệ**, build có thể thất bại trong configuration. Các hướng xử lý là quản lý mọi repository phù hợp trong settings, hoặc dùng bộ lọc `content` **không exclusive** ở pluginManagement khi kiến trúc buildscript cũ buộc phải thêm repository.

Đừng tự động áp dụng `exclusiveContent` vào pluginManagement của một dự án dùng nhiều buildscript repositories cũ mà không kiểm tra tác động. Với project dependencies, chính sách tập trung qua `dependencyResolutionManagement` thường rõ ràng hơn.

## 10. Maven release/snapshot: `mavenContent` khác `content`

Maven repository thường tách artifacts đã release và snapshot.

~~~groovy
repositories {
    maven {
        name = 'releaseRepo'
        url = uri('https://repo.company.example/maven/releases')
        mavenContent {
            releasesOnly()
        }
    }

    maven {
        name = 'snapshotRepo'
        url = uri('https://repo.company.example/maven/snapshots')
        mavenContent {
            snapshotsOnly()
        }
    }
}
~~~

- `releasesOnly()` chỉ cho Gradle tìm Maven releases ở repo đó.
- `snapshotsOnly()` chỉ cho Maven snapshots.
- `mavenContent` dựa vào tính chất Maven snapshot/release; **`content`** lọc tọa độ group/module/version và context theo API.
- Một repo có thể dùng các cơ chế lọc phù hợp cùng nhau khi cần. Không trông đợi Maven snapshot filter tự hiểu “group nội bộ phải độc quyền”.
- `mavenContent` không thay thế `exclusiveContent` nếu cùng một tọa độ nội bộ có thể xuất hiện trong repo không đáng tin.

**Bẫy:** Một snapshot có thể có metadata/unique timestamp build riêng. Khi một module cần reproducibility cao, cân nhắc version cố định, dependency locking và chính sách artifacts immutable; chỉ chia release/snapshot bằng repo không làm nội dung snapshot cố định.

## 11. Bảo mật: giảm dependency confusion nhưng không “chứng minh artifact an toàn”

### 11.1. Những gì filters thực sự giúp

Ví dụ tổ chức sở hữu các nhóm:
- `com.acme` — modules chính;
- `com.acme.security` — libraries nội bộ nhạy cảm;
- `org.example.public` — library public.

Chính sách:

~~~groovy
repositories {
    exclusiveContent {
        forRepository {
            maven {
                url = uri('https://repo.company.example/maven')
            }
        }
        filter {
            includeGroupAndSubgroups 'com.acme'
        }
    }

    mavenCentral()
}
~~~

Nhờ đó tọa độ `com.acme.*` không được gửi sang Maven Central trong quá trình resolution thuộc scope này. Đây là cách hạn chế **name leakage** và **dependency confusion qua chọn repository sai**.

### 11.2. Những gì filter không bảo đảm

- Một repository nội bộ bị xâm nhập vẫn có thể cung cấp artifact độc hại; exclusive chỉ giới hạn nơi tìm, không kiểm tra artifact có sạch.
- HTTPS giúp bảo vệ kết nối, nhưng chưa chứng minh mọi package từ repo đó là an toàn.
- Nếu bạn dùng `mavenLocal()`, `flatDir` hoặc các repository khác ở scope chưa lọc, chúng vẫn có thể ảnh hưởng đến những dependencies ngoài tập exclusive.
- Mẫu cấu hình chỉ có tác dụng **trong scope đã khai**. Plugin dependencies, buildscript dependencies, build-logic included builds và publishing có thể có cấu hình repository riêng.
- Repository order, version ranges, dynamic versions, changing modules, metadata sources và cache vẫn ảnh hưởng tính tái lập.
- Nếu credentials nằm trong script và được commit hoặc log, việc dùng exclusive không giải quyết rò rỉ secrets.

**Hành động bổ sung nên có:** dùng kho đã thẩm định/HTTPS; quản lý xác thực bằng Provider/Gradle credentials và CI secret store; áp dụng dependency verification/checksums hoặc signatures khi phù hợp, dependency locking và constraints cho version; tránh dynamic/SNAPSHOT trong release ổn định; pin Gradle Wrapper và review thay đổi repository policy.

### 11.3. Không nhúng mật khẩu trong repository DSL

**Không nên:**

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/maven')
        credentials {
            username = 'service-user'
            password = 'real-password-should-never-be-here'
        }
    }
}
~~~

Đoạn đó **chỉ minh họa cấu hình sai**; không bao giờ dùng secret thật trong repository, VCS, email hoặc tài liệu.

Hướng an toàn hơn là đọc giá trị từ `providers.gradleProperty(...)`/`providers.environmentVariable(...)` hoặc Gradle credentials API; tránh `println`/`--debug` với secrets. Ví dụ cấu hình có tên `internalRepo` và `PasswordCredentials` của Gradle có thể nhận properties do người dùng/CI cấp theo convention của credentials API. Tùy hạ tầng, còn có header-based credentials, token hoặc mirror proxy; chọn API chính thức thay vì lưu thông tin xác thực trực tiếp.

## 12. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách giải quyết |
| --- | --- | --- |
| `Could not find com.acme:client:1.0` sau khi thêm `exclusiveContent` | Module không tồn tại ở kho exclusive, dù có ở kho khác | Xác nhận đúng coordinates/credentials/URL; sửa dữ liệu kho hoặc policy, **không** tự fallback sang kho ngoài |
| Một dependency công khai không resolve sau khi siết filter | Tất cả repo phù hợp đều exclude group đó | Thêm repository được phép cho group public; xem transitives |
| `includeGroup 'com.acme'` không match `com.acme.feature` | `includeGroup` match chính xác | Dùng `includeGroupAndSubgroups` hoặc regex đúng |
| Maven Central vẫn nhận truy vấn nhóm nội bộ với `content` | Chỉ include ở internal repo, chưa exclude ở Central | Exclude trong **mọi** repo khác, hoặc chuyển sang `exclusiveContent` |
| Regex filter quá rộng | Dùng pattern `com.acme.*` có thể match ngoài ý định | Dùng `includeGroupAndSubgroups` hoặc regex có biên subgroup đúng |
| Cấu hình plugin tìm không ra marker | `pluginManagement` filter không bao gồm plugin marker/implementation groups | Xác định marker coordinates và dependency bắc cầu |
| Cấu hình fail khi thêm `buildscript.repositories` | `pluginManagement` đã dùng exclusive content | Tập trung repo vào settings hoặc dùng non-exclusive plugin content filtering |
| `repositoriesMode FAIL_ON_PROJECT_REPOS` báo lỗi | `build.gradle` vẫn thêm repositories | Chuyển khai repo tập trung vào settings, bỏ repo cục bộ không được phép |
| Release dependency bị đi tìm ở snapshot repo | Chưa khai `mavenContent.releasesOnly`/`snapshotsOnly` thích hợp | Bổ sung đúng bộ lọc cho từng Maven repo |
| Đã khai exclusive nhưng tải artifact không thành công | Module metadata ở repo phù hợp nhưng artifact thiếu; credential/HTTP lỗi | Kiểm tra kho được chọn, POM/artifact integrity, authentication |
| Cùng version lấy được nội dung khác giữa máy | Repo order khác, changing metadata, mavenLocal hoặc mutable artifacts | Centralize repositories, khóa version, verification và repo trust |
| Dependency resolution dùng repo không mong đợi | Filter đặt sai scope (plugins vs project deps) | Xác định `pluginManagement`, `dependencyResolutionManagement`, `buildscript` và các included builds |

### 12.1. Các lệnh kiểm chứng

Trong dự án có Java plugin/application plugin:

~~~bash
./gradlew repositories --help
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew compileJava --info
./gradlew compileJava --refresh-dependencies --info
~~~

**Lưu ý quan trọng về lệnh đầu:** `repositories` không phải task chuẩn có sẵn trong mọi Gradle project. `./gradlew repositories --help` được trình bày ở đây **không phải bước bắt buộc**; nếu build của bạn không có task `repositories` thì lệnh sẽ thất bại. Để xem repo được khai ở đâu, đọc `settings.gradle`/`build.gradle` và task/plugin model của build. Trong script thực tế, nên dựa vào `dependencies`, `dependencyInsight`, `--info` và logs mạng không chứa secrets để kiểm chứng resolution.

Để chẩn đoán theo từng bước:
1. Xác định **dependency group:name:version** chính xác (và plugin marker nếu đó là plugin).
2. Xác định **scope repository**: project dependencies, buildscript, plugin management hay included build.
3. Liệt kê các repository hợp lệ theo **content/exclusive** và **Maven release/snapshot** filters.
4. Kiểm tra URL, authentication và có đúng artifact/metadata trong kho đã chọn không.
5. Kiểm tra **transitive dependencies**: từng module có group riêng; không tự kế thừa repo của cha.
6. Dùng `dependencyInsight` để kiểm tra version selection; xem `--info` khi cần thông tin resolution. Không đăng public logs có token, URL riêng nhạy cảm hoặc headers.
7. Chỉ dùng `--refresh-dependencies` khi cần làm mới cached resolution metadata; **nó không bỏ qua** repository filters và không giúp module ngoài exclusive set được tìm ở kho khác.

**Không đề xuất `mavenLocal()` hoặc thêm Maven Central “cho hết lỗi” nếu lỗi là một module nội bộ bị thiếu ở kho exclusive.** Đó là hành động phá bảo đảm mà filter được tạo ra để giữ.

## 13. Các bài tập có đáp án

### Bài 1 — include không tự exclude

~~~groovy
repositories {
    maven {
        url = uri('https://repo.company.example/maven')
        content {
            includeGroup 'com.acme'
        }
    }
    mavenCentral()
}
~~~

Hỏi: `com.acme:auth:1.0` có thể được tìm ở Maven Central không?

**Đáp án:** Có; không có exclusion tương ứng ở Maven Central. Kho nội bộ include group chỉ giới hạn **chính kho nội bộ**. Nếu group này phải độc quyền, dùng `exclusiveContent`.

### Bài 2 — Group con có được match?

`includeGroup 'com.acme'` có bao gồm `com.acme.web` không?

**Đáp án:** Không. `includeGroup` match exact group. Với Gradle hỗ trợ, dùng `includeGroupAndSubgroups 'com.acme'`.

### Bài 3 — Nhận biết fallback

Có `exclusiveContent` cho `com.acme` trên kho A. Module `com.acme:billing:2.0` bị thiếu tại kho A nhưng có trên Maven Central. Gradle có fallback không?

**Đáp án:** **Không.** Repository khác không thuộc tập exclusive bị loại khỏi nguồn được phép.

### Bài 4 — Transitive dependencies

Module `com.acme:client:1.0` độc quyền ở kho nội bộ và khai dependency bắc cầu `org.slf4j:slf4j-api:2.x`. Module SLF4J có bắt buộc nằm cùng kho nội bộ không?

**Đáp án:** Không. Module bắc cầu được resolve theo **tọa độ riêng**, cần một kho phù hợp cho `org.slf4j`.

### Bài 5 — Plugin marker

Bạn đặt một filter vào `dependencyResolutionManagement.repositories` nhưng Gradle không tìm được plugin id từ `plugins {}`. Vì sao?

**Đáp án:** Plugin resolution dùng scope `pluginManagement.repositories`/cơ chế plugin riêng; filter cho project dependencies không tự chuyển sang scope plugin.

### Bài 6 — Quan hệ include/exclude

Repo A có `includeGroupByRegex 'com\\.acme\\..*'` và `excludeModule 'com.acme.legacy', 'old-api'`. Hỏi có tìm `com.acme.payments:client` và `com.acme.legacy:old-api` trong A không?

**Đáp án:** Module đầu được phép; module sau bị loại vì match exclusion dù group được include.

### Bài 7 — Vì sao policy fail?

`settings.gradle` có `repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)`, nhưng `app/build.gradle` vẫn khai `repositories { mavenCentral() }`. Kết quả?

**Đáp án:** Gradle từ chối thêm repository tại project level theo policy. Xóa/migrate khai báo repo vào settings (hoặc sửa policy có chủ đích).

### Bài 8 — Release/snapshot

Có hai Maven repositories cùng host group nội bộ: một chứa release, một chứa snapshot. Chỉ dùng `includeGroupAndSubgroups` có đủ để Gradle phân biệt snapshot/release không?

**Đáp án:** Không. Dùng thêm `mavenContent { releasesOnly() }` và `mavenContent { snapshotsOnly() }` cho từng kho, đồng thời quyết định group nào có quyền xuất hiện trong hai kho đó.

### Bài 9 — Bẫy “lọc theo domain là đủ”

Repo nội bộ dùng HTTPS và tên miền công ty. `exclusiveContent` có đảm bảo nội dung JAR an toàn không?

**Đáp án:** Không. Exclusive chỉ ràng buộc **nguồn tìm dependency**. Cần trust policy, credentials, artifact verification và quản lý version/metadata.

### Bài 10 — Thiết kế cấu hình mới

Dự án có thư viện công khai `org.apache.commons`, thư viện nội bộ `com.acme.*`, và plugin Gradle nội bộ. Yêu cầu: project deps nội bộ không được leak ra kho công khai, project repos phải tập trung, plugin marker phải được resolve đúng.

**Đáp án hướng dẫn:** đặt `dependencyResolutionManagement.repositories` ở settings, dùng `FAIL_ON_PROJECT_REPOS`, `exclusiveContent` cho group nội bộ và repo công khai cho modules còn lại; cấu hình `pluginManagement.repositories` riêng có xét marker/implementation groups; kiểm tra sự tương thích với buildscript repositories cũ; thêm verification/locking cho các artifact quan trọng. Không sao chép nguyên một filter sang mọi scope rồi cho rằng chắc chắn đúng.

**Tiêu chí hoàn thành:** Bạn diễn đạt được “repository nào được phép chứa group/module này” bằng cả filter và exclusive, hiểu `include` không có tác dụng ngầm trên repo khác, dự đoán được hành vi thiếu module và transitive, có thể chứng minh bằng một project Java 17 chạy thật, đồng thời không hạ cấp chính sách an toàn chỉ để build xanh.

## 14. Checklist áp dụng cho dự án thật

- [ ] Đã phân loại đầy đủ private groups, public groups, plugin marker coordinates và transitive groups cần thiết.
- [ ] Đã chọn `content` khi chỉ giới hạn từng kho, `exclusiveContent` khi cần nguồn duy nhất.
- [ ] Mọi group con quan trọng đều được match (không nhầm `includeGroup` với subgroup).
- [ ] Không có repository công khai ngoài exclusive set được phép phục vụ private coordinates.
- [ ] Các module bắc cầu public có nơi hợp lệ để resolve.
- [ ] `pluginManagement`, project repositories và `buildscript.repositories` được phân biệt rõ.
- [ ] Nếu dùng `exclusiveContent` trong pluginManagement, đã kiểm tra hạn chế thêm buildscript repos.
- [ ] Maven release/snapshot có `mavenContent` đúng và không bị xem như bảo đảm độc quyền.
- [ ] Không hard-code credentials và không bật verbose logs có secrets.
- [ ] Chính sách repository được centralize khi có nhiều subprojects và test bằng dependency graph.
- [ ] Không “giải quyết lỗi” bằng cách thêm repo không tin cậy, sửa filter lỏng hơn hay dùng dynamic versions thiếu kiểm soát.
- [ ] Build local, CI và included builds được kiểm tra theo từng scope/nguồn riêng.

## 15. Tài liệu chính thức

- [Gradle — Filtering Repository Content](https://docs.gradle.org/current/userguide/filtering_repository_content.html): `content`, `exclusiveContent`, `mavenContent` và những cảnh báo của Gradle.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): trust, tránh dependency confusion, include group/subgroups.
- [Gradle — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html): repository order và project vs plugin repositories.
- [Gradle — Centralizing Repository Declarations](https://docs.gradle.org/current/userguide/centralizing_repositories.html): `dependencyResolutionManagement` và `RepositoriesMode`.
- [Gradle — Best Practices for Dependencies](https://docs.gradle.org/current/userguide/best_practices_dependencies.html): khuyến nghị content/exclusive filtering.
- [Gradle — RepositoryContentDescriptor](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/repositories/RepositoryContentDescriptor.html): API include/exclude và điều kiện lọc.
- [Gradle — ExclusiveContentRepository](https://docs.gradle.org/current/javadoc/org/gradle/api/artifacts/repositories/ExclusiveContentRepository.html): `forRepository`, `forRepositories`, `filter`.
- [Gradle — Declaring Dependency Versions](https://docs.gradle.org/current/userguide/declaring_dependency_versions.html): version selection, constraints.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): kiểm tra checksum/signature của dependency.
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html): plugin repositories và marker/implementation modules.
