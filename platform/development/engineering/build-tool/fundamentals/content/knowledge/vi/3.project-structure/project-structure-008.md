# Nhận diện ranh giới một dự án build và một mô-đun

Khi mở một repository Java, ta thường thấy nhiều thư mục như `app`, `domain`, `common`, `infrastructure`, `build-logic` hoặc `service`. Các thư mục này có thể đại diện cho những phần khác nhau của hệ thống, nhưng tên thư mục tự nó chưa cho biết ranh giới build nằm ở đâu. Một thư mục có thể là một project con trong cùng build, một build độc lập được ghép vào bằng composite build, một package nguồn, hoặc chỉ là nơi chứa tài nguyên.

Trong Build Tool Fundamentals, cần phân biệt rõ **build** và **project/module** để biết Gradle đang cấu hình phạm vi nào, task thuộc project nào và dependency nối các phần của hệ thống ra sao.

- **Build** là một đơn vị cấu hình và thực thi của build tool. Nó có thể chứa một project hoặc nhiều project.
- **Project** trong Gradle là một đơn vị cấu hình bên trong build, có plugin, task, dependency configuration, source set và đầu ra riêng.
- **Subproject** là project con được khai báo trong một multi-project build.
- **Module** là từ có nhiều nghĩa tùy ngữ cảnh. Trong Gradle, nó thường được dùng để chỉ một project con; trong Java Platform Module System (JPMS), nó là đơn vị mô-đun ở cấp ngôn ngữ/runtime. Hai cách dùng này không đồng nghĩa.

## 1. Bắt đầu từ ranh giới của build

Một build Gradle thông thường có một thư mục gốc, thường chứa `settings.gradle` hoặc `settings.gradle.kts`. File settings xác định tên build, project gốc và những project con tham gia vào build. Với build một project đơn giản, Gradle cũng có thể dùng cấu hình settings ngầm định khi không có file settings; vì vậy cần nhìn vào cách build thực tế được khởi tạo thay vì chỉ dựa vào một file riêng lẻ.

Ví dụ một build Gradle đơn giản:

```text
hello-build/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   └── java/
    └── test/
        └── java/
```

`hello-build` là thư mục gốc của build và cũng là thư mục của project gốc. Build này chỉ có một project. File `build.gradle` mô tả cấu hình project; source code được đặt trong các source set theo quy ước của plugin Java.

Ví dụ nội dung `settings.gradle`:

```groovy
rootProject.name = 'hello-build'
```

`rootProject.name` đặt tên logic của project gốc. Tên logic này không bắt buộc phải trùng tên thư mục trên ổ đĩa. Khi đọc cấu hình, cần phân biệt tên project với đường dẫn vật lý của thư mục.

Một build có thể có nhiều project. Khi đó settings file đóng vai trò quan trọng vì nó khai báo những project con thuộc build.

## 2. Một build có thể chứa nhiều project

Gradle gọi cấu trúc có một project gốc và nhiều project con là **multi-project build**. Mỗi project con có thể đảm nhiệm một phần chức năng hoặc một thành phần có thể tái sử dụng của hệ thống.

Ví dụ:

```text
shop/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
├── domain/
│   └── build.gradle
└── infrastructure/
    └── build.gradle
```

File `settings.gradle` khai báo các project con:

```groovy
rootProject.name = 'shop'

include 'app', 'domain', 'infrastructure'
```

Sau khai báo này, build có bốn project:

| Project path | Thư mục mặc định | Vai trò minh họa |
|---|---|---|
| `:` | `shop/` | Project gốc, chứa cấu hình chung của build |
| `:app` | `shop/app/` | Ứng dụng có điểm khởi chạy |
| `:domain` | `shop/domain/` | Quy tắc nghiệp vụ và mô hình miền |
| `:infrastructure` | `shop/infrastructure/` | Thành phần tích hợp hạ tầng |

Project path là định danh trong build. Dấu `:` đứng riêng biểu thị project gốc; `:app` là project con có tên `app`. Khi có cấu trúc lồng nhau, path thể hiện từng cấp, ví dụ `:services:orders`.

`include` làm cho Gradle nhận diện các project con trong build. Mặc định, Gradle ánh xạ path `:app` tới thư mục `app` dưới thư mục gốc. Nếu cấu trúc thư mục khác quy ước, có thể ánh xạ project tới thư mục khác bằng `projectDir` trong settings:

```groovy
include 'services:orders'
project(':services:orders').projectDir = file('backend/order-service')
```

Vì vậy, project path và tên thư mục không nhất thiết giống nhau. Khi điều tra một project, hãy xem cả khai báo trong settings lẫn `projectDir` tùy chỉnh nếu có.

## 3. Ranh giới project thể hiện điều gì?

Mỗi Gradle project có phạm vi cấu hình riêng. Project có thể áp dụng plugin khác nhau, khai báo dependency khác nhau, định nghĩa task riêng và tạo đầu ra riêng. Trong project Java, plugin thường tạo các source set và task tương ứng cho mã nguồn chính và mã nguồn kiểm thử.

Ví dụ:

- `:app` có thể áp dụng Application plugin để tạo ứng dụng có điểm khởi chạy.
- `:domain` có thể áp dụng Java Library plugin để đóng gói logic miền thành thư viện.
- `:infrastructure` có thể áp dụng Java Library plugin và khai báo các thư viện dùng để kết nối hệ thống bên ngoài.

Project gốc thường giữ những cấu hình áp dụng chung như quy ước phiên bản plugin, repository, kiểm tra chất lượng hoặc các convention plugin. Tuy nhiên, project gốc không bắt buộc phải chứa mã nguồn ứng dụng. Một project gốc chỉ điều phối build vẫn là project hợp lệ.

Ranh giới project có một số hệ quả thực tế:

1. **Task có project sở hữu.** Task `test` trong `:app` và task `test` trong `:domain` là hai task khác nhau, dù trùng tên.
2. **Dependency được khai báo theo project.** `:app` có thể cần `:domain`, trong khi `:domain` không cần biết về `:app`.
3. **Đầu ra được tách theo project.** Mỗi project thường có thư mục build riêng, ví dụ `app/build/` và `domain/build/`.
4. **Plugin có thể khác nhau.** Không phải project con nào cũng cần cùng loại plugin.
5. **Build có thể phối hợp các project.** Task của project này có thể cần đầu ra từ project khác thông qua project dependency.

## 4. Khai báo dependency giữa các project

Trong multi-project build, một project có thể sử dụng đầu ra của project khác thông qua **project dependency**. Đây là dependency ở cấp build, khác với dependency tới một thư viện bên ngoài được tải từ Maven repository.

Ví dụ, `app` sử dụng các lớp được cung cấp bởi `domain`:

```groovy
// app/build.gradle
plugins {
    id 'application'
}

dependencies {
    implementation project(':domain')
}
```

Project `domain` có thể cấu hình như sau:

```groovy
// domain/build.gradle
plugins {
    id 'java-library'
}
```

`implementation project(':domain')` nói với Gradle rằng `:app` phụ thuộc vào project `:domain`. Gradle có thể nối task cần thiết để biên dịch `:app` sau khi đầu ra thích hợp của `:domain` sẵn sàng. Người viết build không phải tự tìm JAR đã tạo trong thư mục `build/libs` rồi khai báo đường dẫn file thủ công.

Một ví dụ khác là project `infrastructure` cũng phụ thuộc vào `domain` để triển khai các interface do domain định nghĩa:

```groovy
// infrastructure/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    implementation project(':domain')
}
```

Trong thiết kế này, `app` có thể phụ thuộc vào `infrastructure` và `domain`; `infrastructure` phụ thuộc vào `domain`. Hướng dependency nên phản ánh kiến trúc mà nhóm lựa chọn. Build tool giúp thực thi quan hệ được khai báo, nhưng không tự quyết định kiến trúc nghiệp vụ đúng hay sai.

Project dependency có một số lợi ích so với khai báo file JAR cục bộ:

- Gradle biết project nguồn và có thể xây dựng task graph tương ứng.
- Khi mã nguồn project được phụ thuộc thay đổi, đầu ra có thể được tạo lại theo quy tắc build.
- Dependency có thể tham gia vào compile classpath hoặc runtime classpath theo configuration được khai báo.
- Không cần cố định đường dẫn tới một file JAR được tạo từ lần build trước.

Để chạy một task cụ thể trong một project, dùng task path đầy đủ:

```bash
# Liệt kê các project trong build
./gradlew projects

# Chạy build của project app
./gradlew :app:build

# Chạy kiểm thử của project domain
./gradlew :domain:test
```

Task path giúp tránh nhầm lẫn khi nhiều project có task trùng tên. Khi cần tìm project nào sở hữu một task, hãy dùng project path thay vì đoán từ tên task.

## 5. Không phải thư mục con nào cũng là project con

Một điểm dễ gây nhầm là nhìn thấy thư mục con có `build.gradle` rồi kết luận nó tự động thuộc multi-project build. Với Gradle, project con phải được nhận diện trong cấu hình settings của build, thường bằng `include`. Chỉ có thư mục hoặc build script lồng bên trong chưa đủ để kết luận nó là subproject của build hiện tại.

Ví dụ:

```text
repository/
├── settings.gradle
├── app/
│   └── build.gradle
├── docs/
│   └── examples/
│       └── build.gradle
└── scripts/
```

Nếu settings chỉ khai báo `include 'app'`, project `:app` thuộc build hiện tại. `docs/examples` không tự động trở thành project con chỉ vì có file `build.gradle`. Thư mục đó có thể là ví dụ, một build độc lập, hoặc chỉ là file không được build hiện tại sử dụng.

Một thư mục có `settings.gradle` riêng thường là dấu hiệu của một build độc lập. Tuy vậy, để xác định chính xác, cần xem build nào được chạy, thư mục gốc nào được chọn và cấu hình include của build đó.

## 6. Multi-project build và composite build khác nhau

Hai khái niệm này đều cho phép tổ chức nhiều phần trong một lần làm việc, nhưng ranh giới cấu hình khác nhau.

### 6.1. Multi-project build

Trong multi-project build, các project con cùng thuộc một build và được khai báo trong settings của build gốc:

```groovy
// settings.gradle của build chính
rootProject.name = 'shop'
include 'app', 'domain'
```

Các project dùng chung một build lifecycle và được quản lý trong cùng cấu trúc project. Chúng vẫn có build script, task, dependency và đầu ra riêng.

### 6.2. Composite build

Composite build kết hợp nhiều Gradle build độc lập. Mỗi build được include vẫn có cấu hình settings và project riêng. Một build có thể include build khác bằng `includeBuild`:

```groovy
// settings.gradle của build chính
rootProject.name = 'shop'
include 'app', 'domain'
includeBuild 'build-logic'
```

Ví dụ cấu trúc:

```text
workspace/
├── shop/
│   ├── settings.gradle
│   ├── app/
│   └── domain/
└── build-logic/
    ├── settings.gradle
    └── src/
```

`shop` là một build; `build-logic` là một build độc lập được kết hợp vào composite. `build-logic` không trở thành subproject `:build-logic` của `shop`. Nó giữ ranh giới build riêng và thường được dùng để phát triển convention plugin hoặc logic build có thể tái sử dụng.

Composite build cũng có thể hỗ trợ thay thế một module bên ngoài bằng project tương ứng trong build được include, tùy cấu hình và tọa độ dependency. Điều này hữu ích khi phát triển đồng thời một thư viện và ứng dụng tiêu thụ nó mà không phải phát hành thư viện sau mỗi lần sửa.

| Tiêu chí | Multi-project build | Composite build |
|---|---|---|
| Ranh giới | Một build, nhiều project | Nhiều build độc lập được kết hợp |
| Khai báo thường gặp | `include 'app', 'domain'` | `includeBuild 'build-logic'` |
| Settings | Cùng build gốc quản lý các project con | Mỗi build có settings riêng |
| Project path | Các project con có path trong build, ví dụ `:app` | Project thuộc build được include giữ danh tính trong build riêng |
| Trường hợp thường dùng | Chia một hệ thống thành nhiều project có liên hệ chặt chẽ | Ghép các build độc lập, phát triển build logic hoặc thư viện song song |

Không nên dùng hai thuật ngữ thay thế cho nhau. Khi đọc `settings.gradle`, hãy phân biệt `include` với `includeBuild` vì chúng khai báo hai kiểu ranh giới khác nhau.

## 7. Project Gradle không đồng nghĩa với Java module

Từ *module* còn có một ý nghĩa riêng trong Java Platform Module System (JPMS), được giới thiệu từ Java 9. Một Java module mô tả ranh giới đóng gói và truy cập ở cấp nền tảng Java. Nó có thể khai báo module descriptor `module-info.java` với các chỉ thị như `module`, `requires` và `exports`.

Ví dụ:

```java
module com.example.domain {
    exports com.example.domain.model;
}
```

Đoạn khai báo trên định nghĩa Java module tên `com.example.domain` và công khai package `com.example.domain.model` cho module khác. Đây là quy tắc của JPMS khi biên dịch/chạy theo module path.

Gradle project lại là đơn vị cấu hình của build tool. Một Gradle project Java có thể tạo JAR không chứa `module-info.java`, khi đó JAR không phải named module theo JPMS. Một project khác có thể chứa `module-info.java` và tạo artifact có Java module descriptor. Hai khái niệm liên quan nhưng không thể suy ra cái này chỉ từ cái kia.

| Khái niệm | Ranh giới được mô tả | Dấu hiệu thường gặp |
|---|---|---|
| Gradle build | Đơn vị cấu hình và thực thi của Gradle | `settings.gradle` hoặc build được khởi tạo tại thư mục gốc |
| Gradle project | Đơn vị cấu hình bên trong build | Project path như `:app`, build script của project |
| Gradle subproject | Project con trong multi-project build | Khai báo `include` trong settings |
| Java module (JPMS) | Đơn vị module ở cấp Java platform | `module-info.java`, `requires`, `exports` |
| Java package | Nhóm kiểu và namespace trong mã nguồn | Dòng `package ...;` trong file Java |
| Source set | Nhóm mã nguồn và tài nguyên dùng cho một mục đích build | `main`, `test`, source set tùy chỉnh |

Một project có thể có nhiều package và nhiều source set. Nó cũng có thể đóng gói mã nguồn thành một Java module nếu dự án dùng JPMS. Nhưng `src/main/java`, package hay source set không tự tạo ra Gradle subproject.

## 8. Maven cũng có ranh giới project/module

Maven sử dụng mô hình project được mô tả trong `pom.xml`. Một project Maven có thể là project độc lập hoặc tham gia vào một reactor nhiều module. POM cha thường khai báo các module con bằng phần tử `<modules>`:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>shop</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>domain</module>
        <module>app</module>
    </modules>
</project>
```

Trong cấu trúc này, POM gốc có thể đóng vai trò aggregator để Maven nhận diện và điều phối các module trong reactor. Các POM con mô tả từng project con.

Đừng nhầm **aggregator** với **parent**. Aggregator tập hợp các module để tham gia cùng một lần chạy reactor thông qua `<modules>`. Parent cung cấp cấu hình kế thừa thông qua phần tử `<parent>` trong POM con. Một POM có thể vừa là parent vừa là aggregator, nhưng hai vai trò có ý nghĩa khác nhau và không bắt buộc luôn xuất hiện cùng nhau.

Tương tự, từ *module* trong Maven thường chỉ một project thành viên của reactor. Nó vẫn khác Java module theo JPMS. Khi chuyển giữa Gradle và Maven, hãy so sánh ranh giới build/project theo cơ chế của từng công cụ, không chỉ dựa vào cách gọi module.

## 9. Quy trình nhận diện ranh giới trong một repository

Khi được giao đọc hoặc sửa một phần của repository, có thể lần theo các bước sau:

1. **Xác định build đang được chạy.** Tìm thư mục gốc mà lệnh Gradle Wrapper hoặc Maven Wrapper được gọi; xem file settings/POM gốc tương ứng.
2. **Đọc danh sách project thành viên.** Với Gradle, xem `include` và `includeBuild`; với Maven, xem `<modules>` và các POM con.
3. **Xác định project path và thư mục vật lý.** Kiểm tra `projectDir` nếu Gradle có ánh xạ tùy chỉnh.
4. **Mở build script của project cần làm việc.** Xem plugin, task, dependency configuration, source set và đầu ra mà project sở hữu.
5. **Lần theo project dependency.** Xác định project nào sử dụng project nào, và hướng dependency có phù hợp với cấu trúc mong muốn không.
6. **Phân biệt build độc lập và project con.** Nếu thấy `includeBuild` hoặc settings riêng, kiểm tra ranh giới build độc lập.
7. **Kiểm tra JPMS khi cần.** Nếu câu hỏi liên quan đến Java module path hoặc truy cập package, tìm `module-info.java`; không suy ra JPMS từ Gradle project path.

Một số lệnh Gradle hỗ trợ việc nhận diện:

```bash
# Hiển thị project thuộc build hiện tại
./gradlew projects

# Hiển thị task trong một project cụ thể
./gradlew :app:tasks --all

# Hiển thị dependency graph của một project
./gradlew :app:dependencies

# Chạy build cho một project cụ thể
./gradlew :app:build
```

Nếu lệnh được gọi từ một thư mục không phải build root, có thể chỉ định thư mục build bằng `-p`/`--project-dir`. Điều quan trọng là xác định đúng build root trước khi diễn giải kết quả, vì cùng một tên project có thể xuất hiện trong các build độc lập khác nhau.

## 10. Ví dụ tổng hợp: phân tích cấu trúc một hệ thống

Giả sử repository có cấu trúc sau:

```text
commerce-workspace/
├── commerce/
│   ├── settings.gradle
│   ├── build.gradle
│   ├── api/
│   │   └── build.gradle
│   ├── domain/
│   │   └── build.gradle
│   └── persistence/
│       └── build.gradle
└── build-logic/
    ├── settings.gradle
    └── src/main/groovy/
```

Giả sử `commerce/settings.gradle` có nội dung:

```groovy
rootProject.name = 'commerce'
include 'api', 'domain', 'persistence'
includeBuild '../build-logic'
```

Ta có thể phân loại như sau:

- `commerce` là build chính, đồng thời có project gốc `:`.
- `:api`, `:domain` và `:persistence` là các subproject thuộc build `commerce`.
- `build-logic` là một build độc lập được include vào composite build.
- Mỗi project con có thể có task `compileJava`, `test` và `jar` riêng nếu áp dụng Java plugin phù hợp.
- Nếu `api` khai báo `implementation project(':domain')`, đây là project dependency bên trong build `commerce`.
- Nếu `api` sử dụng một convention plugin được cung cấp từ `build-logic`, plugin đó đến từ build được include; `build-logic` không trở thành subproject `:build-logic` của `commerce`.

Nếu `domain/src/main/java` chứa `module-info.java`, đó là dấu hiệu domain còn khai báo một Java module theo JPMS. Chi tiết này không làm thay đổi việc `:domain` là một Gradle project con.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Mỗi thư mục con là một Gradle project | Project con phải được nhận diện trong settings của build; thư mục con đơn thuần chưa đủ |
| Có `build.gradle` nghĩa là thuộc build gốc | Build script có thể nằm trong một build độc lập hoặc thư mục ví dụ không được build gốc include |
| Project gốc luôn chứa ứng dụng chính | Project gốc có thể chỉ giữ cấu hình chung và điều phối các project con |
| `includeBuild` giống `include` | `include` khai báo project con; `includeBuild` kết hợp một build độc lập |
| Gradle project chính là Java module | Gradle project là đơn vị cấu hình build; Java module là ranh giới JPMS được mô tả bằng `module-info.java` |
| Package hoặc source set là module build | Package và source set là các cấu trúc bên trong project, không tự tạo project con |
| Hai task trùng tên là cùng một task | Task thuộc project cụ thể; dùng task path như `:app:test` để xác định rõ |
| Maven parent và aggregator là một khái niệm | Parent phục vụ kế thừa cấu hình; aggregator tập hợp module trong reactor |

## 12. Tự kiểm tra cách đọc cấu trúc

Với cấu trúc ví dụ ở phần 10, hãy thử trả lời:

1. Build chính có bao nhiêu project thuộc multi-project build, tính cả project gốc?
2. `build-logic` là project con hay build độc lập? Dấu hiệu nào trong settings chứng minh điều đó?
3. Muốn chạy kiểm thử riêng của `persistence`, task path nào phù hợp?
4. Nếu `domain` có `module-info.java`, điều đó có thay đổi project path `:domain` không?
5. Nếu thêm một thư mục `docs/examples` chứa `build.gradle` nhưng không khai báo trong settings, có thể kết luận nó là subproject của `commerce` không?

Có thể kiểm chứng câu trả lời cho câu hỏi về project và task bằng `./gradlew projects` và `./gradlew :persistence:tasks --all` khi chạy từ build `commerce`. Với câu hỏi về Java module, hãy đọc `module-info.java` và kiểm tra cách project biên dịch/chạy trên classpath hoặc module path.

Khi đã xác định được build root, danh sách project thành viên, project path và các build được include, ta có thể định vị chính xác cấu hình cần đọc hoặc sửa. Việc phân biệt thêm Gradle project với Java module giúp tránh nhầm lẫn giữa ranh giới do build tool quản lý và ranh giới do nền tảng Java thực thi.
