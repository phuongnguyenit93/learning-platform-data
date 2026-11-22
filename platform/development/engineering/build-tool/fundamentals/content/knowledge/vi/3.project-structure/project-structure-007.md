# Quy ước bố trí thư mục và trường hợp cần cấu hình khác mặc định

Công cụ build cần biết mã nguồn, tài nguyên và mã kiểm thử của dự án nằm ở đâu. Với một dự án Java, Gradle và Maven đều có các quy ước thư mục phổ biến để tự nhận diện những đầu vào này. Khi dự án tuân theo quy ước, bạn thường chỉ cần khai báo plugin và dependency; build tool có thể tìm đúng tệp mà không cần cấu hình từng đường dẫn.

Quy ước giúp dự án dễ đọc, dễ mở trong IDE và dễ chạy trên CI. Tuy nhiên, dự án cũ, mã nguồn được sinh tự động, bộ kiểm thử tích hợp hoặc cấu trúc repository đặc biệt có thể cần đường dẫn khác. Khi đó, hãy cấu hình build tool để nó hiểu chính xác source root và resource root của dự án.

## 1. Cấu trúc thư mục Java phổ biến

Một dự án Java đơn giản dùng Gradle với Java plugin thường có dạng:

```text
my-project/
├── gradlew
├── gradlew.bat
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/app/
    │   │       └── Application.java
    │   └── resources/
    │       └── application.yml
    └── test/
        ├── java/
        │   └── com/example/app/
        │       └── ApplicationTest.java
        └── resources/
            └── test-data.json
```

Trong ví dụ này, `my-project` là thư mục gốc của Gradle project. Các thư mục `src/main` và `src/test` chia mã nguồn dùng khi chạy ứng dụng với mã nguồn chỉ phục vụ kiểm thử.

| Đường dẫn | Vai trò |
|---|---|
| `src/main/java` | Mã nguồn Java chính, được biên dịch để tạo sản phẩm của ứng dụng hoặc thư viện. |
| `src/main/resources` | Tài nguyên dùng khi chạy ứng dụng, chẳng hạn YAML, properties, template, ảnh hoặc tệp dữ liệu. |
| `src/test/java` | Mã nguồn kiểm thử, được biên dịch trong source set `test`. |
| `src/test/resources` | Tài nguyên dành cho test, chẳng hạn dữ liệu mẫu hoặc cấu hình kiểm thử. |
| `build.gradle` | Cấu hình build của project, plugin, dependency và task. |
| `settings.gradle` | Khai báo tên root project và những project con thuộc build. |
| `gradle/wrapper` | Tệp hỗ trợ Gradle Wrapper chọn và tải phiên bản Gradle được dự án khai báo. |
| `gradle.properties` | Các thuộc tính cấu hình Gradle ở phạm vi phù hợp, ví dụ tùy chọn JVM hoặc property của build. |

Tên tệp `settings.gradle.kts` và `build.gradle.kts` được dùng khi viết build script bằng Kotlin DSL. Các tệp `.gradle` tương ứng dùng Groovy DSL.

## 2. Source root và package Java

Build tool cần biết **thư mục gốc chứa mã nguồn** (source root). Với Java plugin mặc định của Gradle, source root của mã chính là `src/main/java`. Các thư mục package nằm bên dưới source root.

Ví dụ:

```text
src/main/java/
└── com/
    └── example/
        └── order/
            └── OrderService.java
```

Nội dung lớp có thể khai báo:

```java
package com.example.order;

public class OrderService {
    public void createOrder() {
        // Xử lý tạo đơn hàng
    }
}
```

Đường dẫn package được tính tương đối từ source root. `src/main/java` không phải một phần của tên package. Vì vậy, lớp trên thuộc package `com.example.order`, không phải `src.main.java.com.example.order`.

Đây là quy ước tổ chức mã nguồn giúp compiler, IDE và công cụ build cùng hiểu cấu trúc dự án. Nếu source root được chuyển sang một thư mục khác, package vẫn có thể giữ nguyên; điều cần cập nhật là cấu hình để build tool nhận diện đúng thư mục gốc mới.

## 3. Source root khác resource root như thế nào?

Mã nguồn và tài nguyên có mục đích khác nhau nên được đặt ở các source root riêng.

**Mã nguồn Java** được compiler xử lý để tạo bytecode. Ví dụ `OrderService.java` được biên dịch thành một hoặc nhiều tệp `.class`.

**Tài nguyên** thường được sao chép vào output của source set để ứng dụng hoặc test đọc khi chạy. Ví dụ `src/main/resources/application.yml` được đưa vào output resource của mã chính. Khi đóng gói JAR, tệp này thường xuất hiện ở đường dẫn `application.yml` trong JAR và có thể được đọc từ classpath.

Tài nguyên kiểm thử ở `src/test/resources` thuộc classpath kiểm thử. Nó phục vụ test và không tự động trở thành tài nguyên production trong JAR của ứng dụng.

Với Java plugin của Gradle, output mặc định thường có dạng:

```text
build/
├── classes/
│   └── java/
│       ├── main/       # Bytecode của mã chính
│       └── test/       # Bytecode của mã kiểm thử
├── resources/
│   ├── main/           # Tài nguyên của mã chính
│   └── test/           # Tài nguyên của test
└── libs/
    └── my-project.jar
```

Tên và nội dung output có thể thay đổi theo plugin hoặc cấu hình. Thư mục `build/` là nơi chứa kết quả được tạo ra; thông thường không nên đặt mã nguồn do lập trình viên viết trực tiếp vào đây vì task `clean` có thể xóa nó.

## 4. Vai trò của các tệp cấu hình ở cấp project

Trong một Gradle build, các tệp cấu hình ở thư mục gốc có trách nhiệm khác nhau:

- `settings.gradle` hoặc `settings.gradle.kts` xác định cấu trúc build: tên root project, project con được đưa vào build và một số thiết lập ở cấp build.
- `build.gradle` hoặc `build.gradle.kts` cấu hình plugin, dependency, source set và task của project tương ứng.
- `gradle.properties` cung cấp các property cấu hình Gradle, chẳng hạn `org.gradle.jvmargs` hoặc property do build script sử dụng.
- `gradle/wrapper/gradle-wrapper.properties` xác định phiên bản Gradle mà Wrapper sẽ sử dụng.
- `gradlew` và `gradlew.bat` là script để chạy build bằng Wrapper trên các hệ điều hành tương ứng.

Không nên nhầm thư mục `src` với thư mục chứa project con. `src/main/java` thường là source root bên trong một project; một project con Gradle là một đơn vị build riêng có thể có build script, dependency và task riêng.

## 5. Cấu trúc dự án nhiều module

Khi ứng dụng lớn hơn, bạn có thể chia build thành nhiều Gradle project, ví dụ `app`, `domain` và `infrastructure`:

```text
shop/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradle/
│   └── wrapper/
├── app/
│   ├── build.gradle
│   └── src/
│       ├── main/java/
│       └── test/java/
├── domain/
│   ├── build.gradle
│   └── src/
│       ├── main/java/
│       └── test/java/
└── infrastructure/
    ├── build.gradle
    └── src/
        ├── main/java/
        └── test/java/
```

Tệp `settings.gradle` có thể khai báo:

```groovy
rootProject.name = 'shop'

include 'app', 'domain', 'infrastructure'
```

Gradle nhận diện ba project con có path lần lượt là `:app`, `:domain` và `:infrastructure`. Mỗi project có thể áp dụng plugin, khai báo dependency và có source set riêng.

### 5.1. Project không đồng nghĩa với package hoặc source set

Ba khái niệm này giải quyết ba vấn đề khác nhau:

| Khái niệm | Phạm vi | Ví dụ |
|---|---|---|
| Gradle project | Một đơn vị cấu hình và thực thi trong build; có project path, plugin, dependency và task. | `:app`, `:domain` |
| Java package | Không gian tên của các lớp Java, thường phản ánh cấu trúc thư mục bên dưới source root. | `com.example.order` |
| Source set | Một nhóm mã nguồn, tài nguyên, classpath và output bên trong một Gradle project. | `main`, `test` |

Một Gradle project có thể chứa nhiều package và nhiều source set. Một build có thể chứa nhiều project, mỗi project lại có các package và source set của riêng nó.

### 5.2. Đổi vị trí thư mục project con

Theo mặc định, `include 'domain'` ánh xạ project `:domain` tới thư mục `domain` bên dưới root project. Nếu repository cần giữ project trong một vị trí khác, có thể ánh xạ rõ ràng trong `settings.gradle`:

```groovy
rootProject.name = 'shop'
include 'domain'

project(':domain').projectDir = file('components/domain-core')
```

Trong ví dụ này, project path vẫn là `:domain`, còn thư mục vật lý chứa build script và source của nó là `components/domain-core`. Tên project path và tên thư mục vì vậy không bắt buộc phải giống nhau.

Chỉ dùng cách ánh xạ này khi cấu trúc repository thực sự cần nó. Cấu hình đường dẫn project con không thay thế cấu hình source root bên trong project đó.

## 6. Quy ước mặc định của Gradle và Maven

Gradle Java plugin và Maven đều theo cấu trúc Java phổ biến. Bảng dưới đây so sánh các đường dẫn mặc định thường gặp:

| Nội dung | Gradle Java plugin | Maven |
|---|---|---|
| Mã Java chính | `src/main/java` | `src/main/java` |
| Tài nguyên chính | `src/main/resources` | `src/main/resources` |
| Mã Java kiểm thử | `src/test/java` | `src/test/java` |
| Tài nguyên kiểm thử | `src/test/resources` | `src/test/resources` |
| Output build | Thường trong `build/` | Thường trong `target/` |
| Tệp cấu hình chính | `build.gradle` / `build.gradle.kts`, `settings.gradle` | `pom.xml` |

Maven thường dùng các phase trong build lifecycle và cấu hình plugin trong `pom.xml`. Gradle Java plugin cung cấp các source set và task tương ứng. Cùng một cấu trúc thư mục phổ biến giúp lập trình viên chuyển giữa hai công cụ dễ dàng hơn, nhưng cú pháp cấu hình và mô hình thực thi của chúng khác nhau.

## 7. Khi nào nên cấu hình khác mặc định?

Giữ cấu trúc mặc định là lựa chọn phù hợp khi dự án mới và không có yêu cầu đặc biệt. Việc thay đổi thư mục có thể hợp lý trong một số trường hợp sau.

### 7.1. Dự án cũ có cấu trúc đã tồn tại

Một repository lâu năm có thể đang đặt mã nguồn trong `source/`, `java/` hoặc `legacy/src/`. Di chuyển toàn bộ mã nguồn có thể ảnh hưởng đến script, IDE, công cụ ngoài hoặc quy trình phát hành. Khi chưa thể chuẩn hóa thư mục, cấu hình source root theo vị trí thực tế giúp build tool tiếp tục biên dịch được.

### 7.2. Mã nguồn được sinh tự động

Một số dự án tạo mã Java từ schema, OpenAPI, protobuf hoặc công cụ sinh mã khác. Mã sinh thường được đặt trong thư mục thuộc `build/`, chẳng hạn `build/generated/`, để phân biệt với mã do con người duy trì.

Khi tích hợp mã sinh, cần kết nối đầu ra của task sinh mã với source set tương ứng và bảo đảm task biên dịch biết phụ thuộc vào đầu ra đó. Plugin chuyên dụng thường đã thiết lập quan hệ này. Nếu tự cấu hình, hãy khai báo đầu vào, đầu ra và quan hệ task rõ ràng để build có thể chạy đúng cả trên máy sạch lẫn CI.

Không nên chỉnh sửa thủ công tệp đã sinh nếu lần build tiếp theo có thể ghi đè. Hãy sửa schema hoặc nguồn đầu vào mà generator sử dụng.

### 7.3. Có bộ kiểm thử tích hợp hoặc kiểm thử chức năng riêng

Một số dự án tách unit test và integration test thành các nhóm riêng vì chúng có thời gian chạy, dependency hoặc môi trường khác nhau. Khi đó, có thể tạo source set riêng như `integrationTest` với mã nguồn và tài nguyên tương ứng.

Việc tạo source set bổ sung cần cấu hình thêm classpath, dependency và task chạy test. Nếu chỉ cần một vài test đặc biệt, trước tiên hãy xem liệu cấu hình test hiện có hoặc plugin của dự án đã hỗ trợ phân loại test hay chưa. Tạo source set mới chỉ khi nó thể hiện một nhóm mã và quy trình thực thi có ý nghĩa riêng.

### 7.4. Tài nguyên nằm ở vị trí khác

Một dự án có thể lưu cấu hình hoặc template dùng khi chạy trong thư mục `config/`, `templates/` hoặc thư mục dùng chung. Nếu các tệp đó cần có mặt trên runtime classpath, hãy khai báo chúng như resource roots. Chỉ đặt tệp trong repository chưa đủ để bảo đảm build tool đóng gói nó vào artifact.

### 7.5. Dùng plugin hoặc ngôn ngữ có quy ước riêng

Plugin Kotlin, Scala, Android hoặc plugin framework có thể bổ sung source set, source root và quy tắc đóng gói riêng. Khi dùng plugin chuyên biệt, hãy theo tài liệu và cấu hình mà plugin cung cấp. Đừng giả định rằng việc cấu hình Java source set sẽ tự động điều khiển mọi ngôn ngữ trong project.

## 8. Cấu hình source set trong Gradle

Với Gradle Java plugin, `sourceSets` là nơi cấu hình các nhóm mã nguồn. Hai source set mặc định thường dùng là `main` và `test`.

### 8.1. Thêm một thư mục nhưng giữ nguyên mặc định

Giả sử dự án vẫn dùng `src/main/java` nhưng cần biên dịch thêm mã Java từ `src/shared/java`, đồng thời nạp thêm tài nguyên từ `config/resources`.

Với Groovy DSL trong `build.gradle`:

```groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            srcDir 'src/shared/java'
        }
        resources {
            srcDir 'config/resources'
        }
    }
}
```

`srcDir` bổ sung thư mục vào tập source directories hiện có. Các thư mục mặc định vẫn được giữ lại. Build tool sẽ xem mã Java ở cả hai source roots và xử lý tài nguyên ở các resource roots đã khai báo.

### 8.2. Thay thế toàn bộ thư mục mặc định

Nếu dự án thật sự dùng cấu trúc cũ và muốn thay source roots mặc định, có thể gán danh sách thư mục mới:

```groovy
sourceSets {
    main {
        java {
            srcDirs = ['legacy/java']
        }
        resources {
            srcDirs = ['legacy/resources']
        }
    }
    test {
        java {
            srcDirs = ['legacy/test']
        }
        resources {
            srcDirs = ['legacy/test-resources']
        }
    }
}
```

Trong cấu hình này, các danh sách source roots mặc định được thay bằng danh sách mới. Nếu vẫn cần dùng một thư mục mặc định, hãy đưa nó vào danh sách hoặc dùng cách bổ sung `srcDir` ở phần trước.

### 8.3. Kotlin DSL

Nếu build script dùng `build.gradle.kts`, cú pháp tương ứng có thể viết:

```kotlin
plugins {
    java
}

sourceSets {
    named("main") {
        java {
            srcDir("src/shared/java")
        }
        resources {
            srcDir("config/resources")
        }
    }
}
```

Hai ví dụ Groovy DSL và Kotlin DSL thể hiện cùng một ý tưởng: thêm source root cho source set `main`. Hãy dùng cú pháp phù hợp với loại build script của project.

### 8.4. Cấu hình riêng cho mã kiểm thử

Nếu mã test nằm trong một thư mục bổ sung, có thể thêm thư mục đó vào source set `test`:

```groovy
sourceSets {
    test {
        java {
            srcDir 'src/test-support/java'
        }
        resources {
            srcDir 'src/test-data'
        }
    }
}
```

Mã trong các thư mục này vẫn thuộc test source set. Nó được biên dịch và đưa vào classpath của test theo cấu hình Java plugin, thay vì trở thành mã chính trong artifact production.

## 9. Cấu hình thư mục nguồn trong Maven

Maven cũng có các đường dẫn mặc định tương tự. Nếu dự án dùng một thư mục mã nguồn chính khác, có thể cấu hình trong `pom.xml`:

```xml
<build>
    <sourceDirectory>legacy/java</sourceDirectory>
    <testSourceDirectory>legacy/test</testSourceDirectory>

    <resources>
        <resource>
            <directory>legacy/resources</directory>
        </resource>
    </resources>

    <testResources>
        <testResource>
            <directory>legacy/test-resources</directory>
        </testResource>
    </testResources>
</build>
```

Ví dụ này thay đường dẫn nguồn và tài nguyên mặc định bằng các thư mục đã chỉ định. Nếu cần nhiều thư mục mã nguồn, Maven thường dùng plugin hỗ trợ bổ sung source root, chẳng hạn `build-helper-maven-plugin`, với cấu hình gắn vào lifecycle phù hợp.

Hãy kiểm tra cấu hình hiệu lực của Maven khi parent POM hoặc plugin cũng thay đổi build. Có thể dùng lệnh:

```bash
./mvnw help:effective-pom
```

Lệnh này hiển thị POM sau khi Maven hợp nhất cấu hình kế thừa và các thiết lập liên quan.

## 10. Cách xác nhận build tool đã nhận đúng thư mục

Sau khi thay đổi source roots, hãy kiểm tra kết quả bằng chính các task build của dự án.

Với Gradle:

```bash
./gradlew tasks
./gradlew clean compileJava --info
./gradlew test
./gradlew clean build
```

Trên Windows, có thể dùng `gradlew.bat` thay cho `./gradlew`.

Các bước trên giúp bạn kiểm tra task hiện có, xem log của quá trình biên dịch, chạy test và thực hiện build đầy đủ. Hãy xác nhận rằng:

- Mã nguồn ở từng source root được đưa vào task biên dịch mong muốn.
- Tài nguyên cần dùng khi chạy xuất hiện trong output hoặc artifact.
- Mã test được biên dịch trong test source set và test có thể đọc tài nguyên kiểm thử.
- Các thư mục output được tạo ở vị trí build dự kiến.
- Build vẫn chạy được sau khi xóa output cũ bằng `clean`.

Nếu IDE đang mở project trong lúc bạn đổi cấu hình, hãy đồng bộ lại Gradle hoặc Maven project để IDE cập nhật source roots và dependency. Việc IDE chưa đồng bộ có thể khiến cây thư mục hoặc gợi ý mã tạm thời không phản ánh cấu hình build mới.

## 11. Lỗi thường gặp khi bố trí thư mục

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tệp `.java` tồn tại nhưng không được biên dịch | Thư mục chứa tệp chưa được khai báo là Java source root. | Kiểm tra `sourceSets` hoặc cấu hình source directory trong Maven. |
| Mã chính biên dịch được nhưng ứng dụng không tìm thấy tệp cấu hình | Tệp nằm ngoài resource roots hoặc đường dẫn trong JAR khác với đường dẫn ứng dụng đang tìm. | Khai báo đúng resource root và kiểm tra đường dẫn bên trong artifact. |
| Test không tìm thấy JSON hoặc YAML mẫu | Tài nguyên nằm ngoài `src/test/resources` và chưa được thêm vào test resources. | Bổ sung test resource root. |
| Mã test bị đóng gói vào artifact production | Mã test bị đặt trong source set `main` hoặc được cấu hình như mã chính. | Đưa mã vào test source set và kiểm tra cấu hình đóng gói. |
| Build trên máy lập trình viên thành công nhưng CI thiếu mã sinh | Task tạo mã chưa được nối với task biên dịch hoặc CI thiếu đầu vào sinh mã. | Khai báo đầu ra và quan hệ phụ thuộc task; bảo đảm generator chạy từ đầu vào được quản lý. |
| IDE đánh dấu thư mục là source nhưng Gradle không biên dịch | IDE có thể lưu đánh dấu riêng hoặc chưa đồng bộ build model. | Kiểm tra cấu hình build và chạy task wrapper từ terminal. |
| `clean` làm mất tệp cần thiết | Mã nguồn hoặc dữ liệu do con người duy trì bị đặt nhầm trong thư mục output `build/`. | Chuyển đầu vào sang thư mục nguồn được quản lý; để `build/` dành cho kết quả sinh ra. |

Một lỗi đáng chú ý là nhầm **đường dẫn tệp trên ổ đĩa** với **đường dẫn tài nguyên trên classpath**. Ví dụ, tệp `src/main/resources/config/app.yml` thường được đặt trong JAR tại `config/app.yml`. Khi đọc từ classpath, ứng dụng cần dùng đường dẫn `config/app.yml`, không phải đường dẫn vật lý `src/main/resources/config/app.yml`.

## 12. Nguyên tắc chọn cấu trúc thư mục

Khi thiết kế hoặc điều chỉnh một dự án, hãy cân nhắc các nguyên tắc sau:

1. **Ưu tiên quy ước phổ biến cho dự án mới.** `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources` giúp thành viên mới nhận diện nhanh cấu trúc.
2. **Tách mã chính khỏi mã kiểm thử.** Điều này giúp classpath, dependency và artifact được quản lý đúng mục đích.
3. **Tách mã nguồn khỏi tài nguyên.** Compiler và bước xử lý resources có đầu vào rõ ràng.
4. **Để output ở thư mục do build tool quản lý.** Mã nguồn duy trì thủ công nên nằm ngoài `build/` hoặc `target/`.
5. **Cấu hình rõ khi có ngoại lệ.** Nếu phải dùng cấu trúc khác mặc định, khai báo trong build script hoặc POM để IDE, terminal và CI cùng nhận được quy tắc.
6. **Kết nối task khi có mã sinh tự động.** Đầu ra generator phải được khai báo và phụ thuộc đúng thứ tự trước khi biên dịch.
7. **Chỉ tạo project con khi cần ranh giới build riêng.** Không cần tạo Gradle project mới chỉ vì muốn tách một package hoặc một thư mục Java.
8. **Kiểm tra trên môi trường sạch.** Chạy build sau `clean` để phát hiện trường hợp máy cá nhân vô tình dựa vào tệp sinh cũ hoặc cấu hình IDE riêng.

## 13. Ví dụ tổng hợp

Giả sử một ứng dụng bán hàng có mã chính theo cấu trúc mặc định, nhưng cần thêm thư mục dùng chung và một thư mục tài nguyên cấu hình riêng:

```text
shop-app/
├── build.gradle
├── settings.gradle
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/shop/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
├── src-shared/
│   └── java/
└── config/
    └── resources/
```

Build script có thể bổ sung hai thư mục này:

```groovy
plugins {
    id 'java'
}

sourceSets {
    main {
        java {
            srcDir 'src-shared/java'
        }
        resources {
            srcDir 'config/resources'
        }
    }
}
```

Sau cấu hình, Gradle biên dịch mã chính từ `src/main/java` và `src-shared/java`; tài nguyên chính được lấy từ `src/main/resources` và `config/resources`. Test vẫn dùng các thư mục mặc định. IDE nhập Gradle project sẽ nhận source roots từ build model, còn CI gọi Gradle Wrapper sẽ sử dụng cùng cấu hình đã lưu trong repository.

## 14. Kết luận

Quy ước thư mục giúp build tool tự tìm mã nguồn, tài nguyên và mã kiểm thử theo một cấu trúc quen thuộc. Với Java plugin của Gradle và Maven, các đường dẫn phổ biến là `src/main/java`, `src/main/resources`, `src/test/java` và `src/test/resources`. Trong Gradle, `settings.gradle` mô tả các project của build, còn `sourceSets` mô tả các nhóm mã nguồn bên trong từng project.

Khi cấu trúc dự án khác mặc định vì lý do rõ ràng như kế thừa mã cũ, mã sinh tự động, integration test hoặc tài nguyên ở vị trí riêng, hãy cấu hình source roots trong build script hoặc POM. Cấu hình đó cần được lưu cùng dự án và kiểm tra bằng Gradle/Maven Wrapper để IDE, terminal và CI cùng hiểu một cấu trúc build.
