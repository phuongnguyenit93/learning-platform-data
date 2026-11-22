# Thư mục gốc dự án, gốc kho mã và thư mục làm việc hiện tại

Khi làm việc với một dự án Java, ta thường nghe các cụm từ *project root*, *repository root* và *current working directory*. Cả ba đều có thể được gọi ngắn gọn là “thư mục gốc” trong giao tiếp hằng ngày, nhưng chúng đại diện cho ba mốc khác nhau. Nhầm lẫn giữa chúng có thể khiến Git không tìm thấy repository, Gradle hoặc Maven chọn nhầm build, script đọc sai file cấu hình hoặc ứng dụng chạy được trong IDE nhưng thất bại ở terminal/CI.

Muốn xác định đúng một đường dẫn, trước tiên cần hỏi: đường dẫn đó được tính từ mốc nào? Mốc ấy thuộc Git, thuộc cấu trúc build hay thuộc tiến trình đang chạy? Khi trả lời được câu hỏi này, ta có thể chọn đúng lệnh và cấu hình cho từng công cụ.

## 1. Ba khái niệm cần phân biệt

### 1.1. Gốc kho mã (repository root)

**Repository root** là thư mục gốc của một kho mã được quản lý bởi hệ thống version control. Trong Git, đó là gốc của working tree. Thư mục này thường chứa thư mục hoặc dấu hiệu quản lý `.git`, cùng với những thư mục, file và tài liệu được quản lý trong cùng repository.

Ví dụ một repository có thể chứa nhiều dự án hoặc nhiều build độc lập:

```text
company-workspace/             # Git repository root
├── .git/
├── README.md
├── java-learning/
│   ├── settings.gradle
│   ├── gradlew
│   ├── build.gradle
│   └── module/
├── learning-platform/
│   ├── package.json
│   └── src/
└── scripts/
```

Trong ví dụ này, `company-workspace/` là gốc repository Git. Nó là mốc mà Git dùng để quản lý các file trong working tree. Thư mục `java-learning/` vẫn có thể là gốc của một Gradle build nằm bên trong repository đó.

Repository root không nhất thiết phải chứa `build.gradle`, `settings.gradle` hoặc `pom.xml`. Một repository có thể là monorepo, chứa nhiều ứng dụng, thư viện, tài liệu và công cụ. Cũng có thể có một repository chỉ chứa đúng một dự án, khi ấy repository root và thư mục gốc dự án tình cờ trùng nhau.

Trong Git, có thể hỏi vị trí gốc working tree bằng:

```bash
git rev-parse --show-toplevel
```

Trên PowerShell cũng chạy cùng lệnh Git:

```powershell
git rev-parse --show-toplevel
```

Lệnh này phải được gọi bên trong working tree của repository. Nếu thư mục hiện tại không thuộc repository nào, Git sẽ báo lỗi. Tùy chọn `-C` cho phép chỉ định thư mục để Git thực hiện lệnh mà không cần chuyển thư mục terminal:

```bash
git -C /work/company-workspace/java-learning status
```

```powershell
git -C 'D:\work\company-workspace\java-learning' status
```

Git tìm repository từ vị trí được chỉ định và các thư mục cha theo quy tắc của nó. Vì vậy, chạy `git status` ở một thư mục con vẫn có thể thao tác với repository cha. Kết quả đường dẫn có thể được trình bày tương đối với thư mục hiện tại hoặc theo cách Git chọn, nhưng repository được nhận diện vẫn là cùng một working tree.

### 1.2. Gốc dự án hoặc gốc build (project/build root)

Trong giao tiếp thông thường, **project root** thường là thư mục chứa cấu hình chính và cấu trúc của một dự án. Với dự án Gradle hoặc Maven, đây thường là nơi có build descriptor hoặc file settings tương ứng. Tuy nhiên, cần xem công cụ đang dùng và cấu hình thực tế để xác định chính xác mốc đó.

Với Gradle, có một khái niệm cụ thể hơn là **root project** của một build. Trong build nhiều project, root project là project cấp cao nhất; các project con được khai báo qua `settings.gradle` hoặc `settings.gradle.kts`. Thư mục của build thường được gọi là `rootDir`, còn thư mục của từng project được biểu diễn bằng `projectDir`.

Ví dụ:

```text
java-learning/                    # Gradle build root / root project directory
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── app/
│   └── build.gradle              # subproject :app
└── domain/
    └── build.gradle              # subproject :domain
```

Trong ví dụ này:

- `java-learning/` là thư mục gốc của Gradle build và thư mục của root project.
- `app/` là thư mục của subproject `:app`.
- `domain/` là thư mục của subproject `:domain`.
- `settings.gradle` mô tả tên root project và những project tham gia build.

Nội dung `settings.gradle` có thể là:

```groovy
rootProject.name = 'java-learning'

include 'app', 'domain'
```

Tên root project (`rootProject.name`) và đường dẫn thư mục root (`rootDir`) có liên quan nhưng không phải cùng một thứ. Đổi tên project không đồng nghĩa với việc chuyển thư mục trên ổ đĩa. Tương tự, tên thư mục `java-learning` không tự quyết định tên project nếu settings đặt một tên khác.

Với Maven, thư mục dự án thường là thư mục chứa `pom.xml`. Trong mô hình multi-module, một POM cha có thể đóng vai trò aggregator, khai báo các module con:

```text
shop-system/                      # thư mục aggregator (có thể đồng thời là parent POM)
├── pom.xml
├── shop-api/
│   └── pom.xml
├── shop-domain/
│   └── pom.xml
└── shop-data/
    └── pom.xml
```

POM ở `shop-system/` có thể khai báo:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>shop-system</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>shop-api</module>
        <module>shop-domain</module>
        <module>shop-data</module>
    </modules>
</project>
```

Trong Maven, cần phân biệt POM đang được chọn, thư mục base của project tương ứng và các module mà aggregator đưa vào reactor. Không phải cứ có nhiều `pom.xml` trong repository thì tất cả đều thuộc cùng một lần build; quan hệ module phải được cấu hình hoặc được chọn rõ ràng.

Do đó, khi nói “gốc dự án”, hãy nêu cụ thể hơn nếu có thể: thư mục chứa `settings.gradle`, thư mục chứa POM aggregator, thư mục của module `:app`, hay thư mục source của ứng dụng. Những mốc này có thể khác nhau trong một repository lớn.

### 1.3. Thư mục làm việc hiện tại (current working directory)

**Current working directory (CWD)** là thư mục mà một tiến trình đang coi là vị trí làm việc hiện tại. Đây là trạng thái của tiến trình, không phải thuộc tính cố định của repository hay dự án.

Khi mở terminal, shell có một thư mục hiện tại. Khi shell khởi chạy Java, Gradle, Maven hoặc một script, tiến trình con thường nhận thư mục hiện tại từ tiến trình cha, trừ khi lệnh khởi chạy hoặc cấu hình thay đổi nó. Một đường dẫn tương đối như `./config/application.yml` thường được diễn giải từ CWD của tiến trình đang mở file.

Kiểm tra CWD trong shell:

```bash
pwd
```

Trong PowerShell:

```powershell
Get-Location
```

Trong Java, có thể quan sát thư mục làm việc của JVM:

```java
public class WorkingDirectoryExample {
    public static void main(String[] args) {
        System.out.println(System.getProperty("user.dir"));
    }
}
```

`user.dir` thường phản ánh working directory mà JVM nhận khi khởi chạy. Nó không nhất thiết là nơi chứa file `.java`, file `.class`, file JAR hoặc file cấu hình của build.

Ví dụ, cùng một chương trình có thể được chạy từ hai vị trí:

```text
/work/shop-system
    └── config/application.yml

/work
```

Nếu CWD là `/work/shop-system`, đường dẫn tương đối `config/application.yml` trỏ đến `/work/shop-system/config/application.yml`. Nếu CWD là `/work`, cùng chuỗi đường dẫn trỏ đến `/work/config/application.yml`. Chương trình không tự biết người viết muốn lấy file cạnh JAR hay cạnh source; điều đó phải được quy định trong ứng dụng hoặc trong cách khởi chạy.

## 2. Quan hệ giữa ba mốc trong cùng một workspace

Một cấu trúc thực tế có thể đặt build ở sâu bên trong repository:

```text
workspace/                              # repository root
├── .git/
├── README.md
├── java-learning/                      # Gradle build root
│   ├── settings.gradle
│   ├── gradlew
│   ├── build.gradle
│   └── module/
│       └── sample-app/
│           └── build.gradle            # Gradle subproject :sample-app
└── tools/
    └── local-check.ps1
```

Giả sử terminal đang đứng tại `workspace/tools/`. Khi ấy:

| Khái niệm | Vị trí | Công cụ/ý nghĩa |
|---|---|---|
| Repository root | `workspace/` | Git quản lý working tree |
| Gradle build root | `workspace/java-learning/` | Gradle tìm settings và cấu hình root build |
| Subproject directory | `workspace/java-learning/module/sample-app/` | Thư mục của project `:sample-app` |
| Current working directory | `workspace/tools/` | Mốc mặc định cho đường dẫn tương đối của shell và tiến trình hiện tại |

Không có gì sai khi bốn mốc này khác nhau. Vấn đề chỉ xuất hiện khi một lệnh hoặc một file cấu hình được viết với giả định về mốc không đúng.

Một repository có thể chứa nhiều build độc lập:

```text
workspace/                         # một Git repository
├── .git/
├── backend/
│   ├── settings.gradle            # Gradle build A
│   └── gradlew
├── admin-tool/
│   ├── settings.gradle            # Gradle build B
│   └── gradlew
└── documentation-site/
    └── package.json               # một dự án frontend
```

Trong trường hợp này, Git có một repository root, nhưng có nhiều project/build root. Không thể suy ra build nào cần chạy chỉ từ vị trí repository root; cần chọn đúng thư mục build hoặc chỉ định rõ cho công cụ.

## 3. Đường dẫn tuyệt đối và đường dẫn tương đối

Ba khái niệm trên thường gây nhầm lẫn khi kết hợp với đường dẫn. Một đường dẫn có thể là tuyệt đối hoặc tương đối.

### 3.1. Đường dẫn tuyệt đối

Đường dẫn tuyệt đối mô tả vị trí bắt đầu từ gốc của hệ thống file hoặc một volume/ổ đĩa. Ví dụ:

```text
/work/company-workspace/java-learning/settings.gradle
```

Trên Windows:

```text
D:\work\company-workspace\java-learning\settings.gradle
```

Đường dẫn tuyệt đối không phụ thuộc CWD của shell. Tuy nhiên, nó phụ thuộc hệ điều hành, ổ đĩa, mount point và cấu trúc máy. Đường dẫn tuyệt đối trên máy lập trình viên có thể không tồn tại trong CI hoặc trên máy đồng đội.

### 3.2. Đường dẫn tương đối

Đường dẫn tương đối mô tả vị trí tính từ một thư mục cơ sở. Trong shell, thư mục cơ sở thông thường là CWD.

Hai ký hiệu cơ bản:

- `.` đại diện cho thư mục hiện tại.
- `..` đại diện cho thư mục cha.

Ví dụ, nếu CWD là `/work/company-workspace/tools/`:

```bash
cd ..
cd ../java-learning
ls ./module
```

Lệnh `cd ..` chuyển shell lên thư mục cha. `cd ../java-learning` chuyển sang thư mục `java-learning` nằm cạnh thư mục `tools`. `ls ./module` liệt kê `module` bên trong CWD hiện tại.

PowerShell sử dụng các khái niệm tương tự:

```powershell
Set-Location ..
Set-Location ..\java-learning
Get-ChildItem .\module
```

Một điểm cần nhớ: ý nghĩa của đường dẫn tương đối phụ thuộc API hoặc công cụ đang xử lý nó. Đối với shell, đường dẫn tương đối thường tính từ CWD. Nhưng Gradle `Project.file(...)` thường giải quyết đường dẫn tương đối theo thư mục của project tương ứng; Maven cũng có nhiều biểu thức và cấu hình được giải quyết theo `project.basedir`/POM base directory. Vì vậy, không nên mặc định mọi chuỗi đường dẫn trong mọi file cấu hình đều tính từ CWD.

### 3.3. Chuẩn hóa và kiểm tra đường dẫn

Khi debug, hãy biến một đường dẫn tương đối thành đường dẫn tuyệt đối để biết chương trình thực sự đang tìm ở đâu. Trong Java NIO:

```java
import java.nio.file.Path;

public class PathExample {
    public static void main(String[] args) {
        Path relative = Path.of("config", "application.yml");
        Path absolute = relative.toAbsolutePath().normalize();

        System.out.println("Relative: " + relative);
        System.out.println("Absolute: " + absolute);
        System.out.println("Exists: " + java.nio.file.Files.exists(absolute));
    }
}
```

`toAbsolutePath()` bổ sung CWD hiện tại để tạo đường dẫn tuyệt đối. `normalize()` loại bỏ các thành phần dư thừa như `.` hoặc cặp `folder/..` ở mức cú pháp. Nó không đảm bảo file tồn tại và cũng không nhất thiết giải quyết symbolic link thành đường dẫn vật lý thực tế. Muốn kiểm tra file, có thể dùng `Files.exists(...)` hoặc các API kiểm tra phù hợp.

Trên Windows, dấu phân cách thường là `\`; trên Linux/macOS thường là `/`. Java `Path.of(...)` và `Paths.get(...)` giúp xử lý đường dẫn theo hệ điều hành đang chạy. Tránh ghép chuỗi đường dẫn bằng cách tự chèn dấu `/` hoặc `\` khi có thể dùng API `Path.resolve(...)`.

## 4. Công cụ build xác định project root như thế nào?

Shell, Git, Gradle và Maven có mục tiêu khác nhau, nên cách chúng chọn thư mục gốc cũng khác nhau. Không nên lấy kết quả của một công cụ làm bằng chứng duy nhất cho mốc của công cụ khác.

### 4.1. Gradle: settings, root project và project directory

Gradle sử dụng file settings (`settings.gradle` hoặc `settings.gradle.kts`) để xác định cấu trúc build nhiều project. Thư mục chứa settings được dùng làm thư mục gốc của build trong cấu hình thông thường. Từ đó Gradle biết root project và các subproject.

Ví dụ:

```groovy
// settings.gradle
rootProject.name = 'shop-system'
include 'app', 'domain'
```

Với cấu trúc:

```text
shop-system/
├── settings.gradle
├── build.gradle
├── app/
│   └── build.gradle
└── domain/
    └── build.gradle
```

Gradle có thể hiển thị cấu trúc project bằng:

```bash
./gradlew projects
```

Để chọn thư mục build rõ ràng từ bất kỳ CWD nào, dùng `-p` hoặc `--project-dir`:

```bash
gradle -p /work/company-workspace/java-learning projects
```

Nếu đang dùng Wrapper, có thể gọi file Wrapper bằng đường dẫn phù hợp và truyền project directory:

```bash
../gradlew -p .. projects
```

Ví dụ trên giả định CWD là thư mục con nằm ngay bên trong Gradle build root và Wrapper nằm ở thư mục cha. `-p ..` chỉ định Gradle build root là thư mục cha; đường dẫn tới `../gradlew` là cách shell tìm script Wrapper. Hai đường dẫn này phục vụ hai mục đích khác nhau.

Các giá trị trong Gradle có thể được in ra từ build script để kiểm tra:

```groovy
tasks.register('showProjectLocations') {
    doLast {
        println "rootProject.name = ${rootProject.name}"
        println "rootDir          = ${rootDir}"
        println "project.name     = ${project.name}"
        println "projectDir       = ${projectDir}"
    }
}
```

Khi chạy task ở root project, `rootDir` là thư mục gốc build và `projectDir` là thư mục project hiện tại. Nếu task được đăng ký trong subproject, `projectDir` sẽ là thư mục subproject đó; `rootDir` vẫn trỏ đến gốc build chung.

Gradle Wrapper và Gradle build root cũng là hai điều khác nhau. Wrapper là script cùng cấu hình phân phối Gradle, thường nằm trong repository/build root. Shell cần tìm được script đó để khởi chạy. Sau khi chạy, Gradle xác định build cần xử lý dựa trên thư mục được chọn, settings và các tham số như `-p`. Có thể gọi một Wrapper bằng đường dẫn tuyệt đối khi CWD nằm ở nơi khác.

### 4.2. Maven: POM được chọn và project base directory

Maven thường tìm `pom.xml` trong CWD nếu người dùng không chỉ định file khác. Vì thế, chạy:

```bash
mvn package
```

ở thư mục nào sẽ khiến Maven mặc định tìm POM tại thư mục đó. Nếu thư mục hiện tại không có `pom.xml`, lệnh có thể thất bại với thông báo không tìm thấy POM.

Có thể chỉ định POM bằng `-f` hoặc `--file`:

```bash
mvn -f /work/company-workspace/shop-system/pom.xml package
```

Hoặc từ một thư mục con:

```bash
mvn -f ../pom.xml package
```

Lúc này Maven sử dụng POM được chỉ định làm project đầu vào. Trong multi-module build, POM aggregator có thể đưa các module con vào reactor theo phần `<modules>`. Nếu chỉ gọi POM của một module con, phạm vi build có thể khác với việc gọi POM aggregator.

Maven cung cấp thuộc tính `${project.basedir}` để tham chiếu thư mục của project hiện tại. Trong POM aggregator, nó tương ứng thư mục chứa POM aggregator; trong POM module, nó tương ứng thư mục của module đó. Khi viết cấu hình Maven, dùng các thuộc tính theo ngữ nghĩa của Maven thường ổn định hơn việc giả định CWD của tiến trình luôn trùng thư mục chứa POM.

### 4.3. Build root không được suy ra chỉ từ repository root

Một Git repository có thể chứa nhiều `settings.gradle`, nhiều `pom.xml` hoặc nhiều công cụ build. Việc Git tìm thấy `.git` ở thư mục cha không có nghĩa Gradle/Maven phải chọn build ở chính thư mục đó.

Ví dụ:

```text
monorepo/
├── .git/
├── service-a/
│   ├── settings.gradle
│   └── gradlew
├── service-b/
│   ├── pom.xml
│   └── mvnw
└── shared-docs/
```

Ở đây Git root là `monorepo/`; Gradle build root là `service-a/`; Maven project root được chọn là `service-b/`. Đây là cấu trúc hợp lệ và phổ biến trong repository chứa nhiều thành phần.

## 5. CWD ảnh hưởng đến lệnh, script và ứng dụng ra sao?

### 5.1. Shell giải quyết đường dẫn trước khi chạy chương trình

Khi gõ:

```bash
./gradlew build
```

shell tìm file `gradlew` tương đối với CWD hiện tại, rồi khởi chạy script. Nếu script không tồn tại tại vị trí đó, shell báo lỗi trước khi Gradle có cơ hội xử lý build.

Tương tự, lệnh:

```bash
./scripts/build.sh
```

đòi hỏi đường dẫn `scripts/build.sh` tồn tại tương đối với CWD. Đường dẫn đến script và CWD sau khi script bắt đầu là hai khái niệm riêng. Script có thể tự `cd` sang thư mục khác, hoặc gọi một tiến trình con với working directory được thiết lập riêng.

Để gọi script bằng đường dẫn tuyệt đối:

```bash
/work/company-workspace/java-learning/gradlew -p /work/company-workspace/java-learning build
```

Việc gọi Wrapper bằng đường dẫn tuyệt đối giúp shell tìm đúng file; tham số `-p` giúp Gradle chọn đúng build root. Khi cần thao tác từ một script chạy ở nhiều nơi, có thể xác định thư mục của chính script rồi truyền đường dẫn đó thay vì giả định CWD.

### 5.2. Ứng dụng Java đọc file theo working directory

Ví dụ:

```java
String configPath = "config/application.yml";
Path path = Path.of(configPath);
System.out.println(path.toAbsolutePath());
```

Nếu chương trình đọc file bằng đường dẫn tương đối, file được tìm theo quy tắc của API và working directory của tiến trình. Khi chạy từ IDE, working directory thường được lưu trong Run Configuration. Khi chạy bằng `java -jar`, working directory thường là thư mục terminal đang đứng tại thời điểm gọi lệnh, trừ khi cách khởi chạy thiết lập khác.

Ví dụ:

```bash
cd /opt/shop
java -jar shop-service.jar
```

Nếu ứng dụng đọc `./config/application.yml`, nó sẽ tìm dưới `/opt/shop/config/application.yml`. Nếu gọi JAR bằng đường dẫn tuyệt đối nhưng CWD là `/tmp`, file tương đối sẽ được tìm dưới `/tmp/config/application.yml`, không tự động chuyển sang thư mục chứa JAR.

Trong ứng dụng Spring Boot, vị trí cấu hình còn chịu ảnh hưởng của cơ chế cấu hình Spring Boot, tham số dòng lệnh, biến môi trường và các thuộc tính cấu hình. Vì vậy, khi một file cấu hình không được tìm thấy, cần kiểm tra cả working directory, đường dẫn cấu hình đã khai báo và cách Spring Boot được khởi chạy.

### 5.3. IDE có thể đặt CWD riêng

IDE thường lưu Run Configuration cho từng ứng dụng hoặc task. Một cấu hình có thể chỉ rõ:

- Main class hoặc module classpath.
- JDK dùng để chạy.
- Program arguments và VM options.
- Environment variables.
- Working directory.

Vì thế, việc bấm Run trong IDE không đảm bảo dùng cùng CWD với terminal. Hai cách chạy có thể cùng dùng một class và một JDK nhưng đọc file cấu hình khác nhau vì working directory khác nhau.

Khi ứng dụng chạy trong IDE nhưng lỗi khi chạy từ terminal, hãy in `System.getProperty("user.dir")` ở cả hai cách chạy để so sánh. Sau đó kiểm tra đường dẫn tương đối mà ứng dụng đang mở. Nếu đường dẫn đó là dữ liệu cần thiết khi triển khai, nên thiết kế cách cấu hình rõ ràng thay vì phụ thuộc vào vị trí terminal tình cờ.

### 5.4. CI/CD cũng có working directory

CI runner thường checkout repository vào một thư mục do hệ thống quản lý. Job có thể chạy ở repository root theo mặc định, hoặc đặt `working-directory` cho một bước. Nếu build nằm trong subdirectory, pipeline cần chuyển đến đúng thư mục hoặc truyền tham số chọn build root.

Ví dụ về ý tưởng cấu hình trong workflow:

```yaml
steps:
  - name: Build backend
    working-directory: java-learning
    run: ./gradlew build
```

Ở bước này, shell chạy trong `java-learning/`. Git vẫn quản lý repository root ở thư mục checkout bên ngoài. Việc `working-directory` chỉ thay đổi CWD cho bước đó; nó không chuyển repository root hay thay đổi nội dung cấu hình Gradle.

Với PowerShell script, có thể chủ động chuyển thư mục trước khi chạy:

```powershell
Push-Location 'D:\work\company-workspace\java-learning'
try {
    .\gradlew.bat build
}
finally {
    Pop-Location
}
```

`Push-Location` lưu vị trí trước đó và chuyển đến thư mục build; `Pop-Location` khôi phục vị trí cũ kể cả khi khối lệnh kết thúc qua lỗi. Điều này hữu ích khi script cần chạy nhiều công cụ ở các thư mục khác nhau.

## 6. Cách xác định đúng thư mục khi bắt đầu làm việc

Thay vì đoán từ tên folder, hãy xác định từng mốc bằng công cụ sở hữu nó.

### Bước 1: Xác định CWD của terminal

Linux/macOS:

```bash
pwd
```

PowerShell:

```powershell
Get-Location
```

Đây là vị trí mà các đường dẫn tương đối của shell sẽ bắt đầu.

### Bước 2: Xác định Git repository root

```bash
git rev-parse --show-toplevel
```

Nếu lệnh thất bại, có thể terminal không nằm trong Git working tree, repository chưa được clone/khởi tạo hoặc đang ở một vị trí khác. Không tự kết luận rằng thư mục hiện tại là project root chỉ vì nó có mã nguồn.

### Bước 3: Tìm build descriptor/settings

Từ cấu trúc dự án, tìm các file như:

```text
settings.gradle
settings.gradle.kts
build.gradle
build.gradle.kts
pom.xml
gradlew
mvnw
```

Một repository có thể có nhiều file cùng tên ở các thư mục con. Hãy xác định file nào thuộc build đang cần chạy, và đọc quan hệ module/settings liên quan nếu cần.

### Bước 4: Chọn build root một cách tường minh

Gradle:

```bash
./gradlew -p /path/to/java-learning projects
./gradlew -p /path/to/java-learning :app:build
```

Maven:

```bash
mvn -f /path/to/shop-system/pom.xml validate
mvn -f /path/to/shop-system/pom.xml package
```

`projects` là task Gradle hữu ích để xem các project trong build. Maven không có goal `projects` mặc định tương đương; ví dụ Maven ở trên dùng phase `validate` để minh họa việc chỉ định POM. Nếu cần xem reactor/module của Maven, có thể dùng log của Maven hoặc plugin phù hợp với môi trường dự án.

### Bước 5: Kiểm tra working directory của tiến trình

Nếu lỗi liên quan đến file không tìm thấy, in CWD hoặc đường dẫn tuyệt đối trước khi đọc file. Với Java, kiểm tra `user.dir`; với shell, dùng `pwd`/`Get-Location`; với IDE, xem trường Working directory trong Run Configuration.

## 7. Những nhầm lẫn thường gặp và cách xử lý

| Triệu chứng | Nhầm lẫn có thể xảy ra | Cách kiểm tra hoặc sửa |
|---|---|---|
| `git status` hoạt động nhưng `./gradlew` không tìm thấy | Đang ở repository root nhưng Wrapper nằm trong thư mục build con | Chuyển vào thư mục có Wrapper hoặc gọi Wrapper bằng đường dẫn tương đối/tuyệt đối phù hợp |
| Gradle báo không tìm thấy build/settings | CWD hoặc `-p` trỏ đến sai build root | Xác định thư mục chứa settings rồi truyền `-p` |
| Maven báo không có POM | CWD không chứa `pom.xml` được chọn | Chuyển thư mục hoặc dùng `mvn -f path/to/pom.xml ...` |
| Ứng dụng không đọc được file cấu hình | Đường dẫn tương đối được tính từ CWD khác dự kiến | In `user.dir`, chuẩn hóa đường dẫn và kiểm tra Run Configuration |
| Chạy được trong IDE nhưng thất bại trong CI | IDE và CI dùng CWD, biến môi trường hoặc JDK khác nhau | So sánh working directory, JDK, arguments và file có trong checkout |
| Script hoạt động khi gọi từ một thư mục nhưng lỗi ở nơi khác | Script giả định CWD luôn là thư mục chứa script | Xác định thư mục script hoặc truyền đường dẫn đầu vào rõ ràng |
| Git root và Gradle root khác nhau | Repository chứa build trong thư mục con hoặc nhiều build | Xem đây là hai mốc độc lập và chọn đúng mốc cho từng lệnh |

Một lỗi phổ biến là viết script như sau:

```bash
#!/usr/bin/env bash
./gradlew build
```

Script này giả định CWD lúc gọi script là thư mục chứa `gradlew`. Nếu người dùng gọi script từ nơi khác, `./gradlew` có thể không tồn tại. Một cách chắc chắn hơn là xác định thư mục của script rồi dùng nó để tìm Wrapper. Trên Bash:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"${SCRIPT_DIR}/gradlew" -p "${SCRIPT_DIR}" build
```

Ví dụ này giả định script được đặt cạnh `gradlew` và settings của build. Nếu script nằm trong `scripts/` còn build root ở thư mục cha, cần điều chỉnh `SCRIPT_DIR/..` theo cấu trúc thực tế. Ý chính là lấy vị trí của script làm mốc có chủ đích thay vì ngầm dựa vào CWD.

## 8. Một số lưu ý về cấu trúc repository và build

### 8.1. Monorepo và nhiều build độc lập

Monorepo là một repository chứa nhiều thành phần có thể được phát triển hoặc build độc lập. Vì vậy, repository root thường là mốc chung cho quản lý mã nguồn, script dùng chung, CI path filters và tài liệu; mỗi ứng dụng/module có thể có project root hoặc build root riêng.

Khi viết CI, hãy xác định pipeline đang cần build thành phần nào. Một bước có thể chạy `git diff` từ repository root nhưng chạy Gradle ở `backend/`. Đây là hai thao tác hợp lệ với hai working directory hoặc hai cách chỉ định đường dẫn khác nhau.

### 8.2. Multi-project build và project con

Trong một Gradle multi-project build, root project điều phối các subproject. Mỗi subproject có thể có `projectDir` riêng và build script riêng. Không nên nhầm thư mục con của project với một Gradle build độc lập: một thư mục có `build.gradle` không tự động là build độc lập nếu settings của build cha đã đưa nó vào như subproject.

Tương tự, Maven aggregator có thể điều phối module con. Một module con có POM riêng, nhưng khi được gọi từ aggregator, nó tham gia Maven reactor của lần build cha. Gọi POM con trực tiếp có thể tạo ra phạm vi và thứ tự thực thi khác.

### 8.3. Thư mục nguồn không phải project root

Trong Java, `src/main/java` thường là source directory/source root theo quy ước build. Đây là nơi đặt package và mã nguồn, không phải thư mục gốc repository hay build. `src/test/java` là source root cho test. Thư mục `build/` của Gradle hoặc `target/` của Maven là thư mục đầu ra được tạo bởi build, cũng không phải build root.

Phân biệt các mốc này giúp tránh đặt file cấu hình ở sai chỗ hoặc dùng đường dẫn tương đối sai. Ví dụ, `src/main/resources/application.yml` là resource thuộc source set; `build/resources/main/application.yml` là bản đã được xử lý/copy vào output; vị trí ứng dụng đọc file khi chạy còn tùy classpath và cấu hình runtime.

### 8.4. Thư mục `.git` có thể không phải thư mục thông thường

Trong Git worktree hoặc submodule, `.git` có thể là một file trỏ đến metadata ở vị trí khác thay vì một thư mục chứa toàn bộ dữ liệu Git. Vì thế, không nên xác định repository root bằng cách chỉ tìm một thư mục tên `.git` ở cấp hiện tại. Hãy dùng `git rev-parse --show-toplevel` để hỏi Git.

Ngoài ra, một thư mục con có thể là repository lồng nhau hoặc submodule với metadata riêng. Khi đó, Git root của thư mục con có thể khác Git root của workspace bên ngoài. Dùng lệnh Git tại đúng vị trí sẽ cho biết repository nào đang được nhận diện.

## 9. Ví dụ thực hành: chạy đúng build từ nhiều vị trí

Giả sử workspace có cấu trúc:

```text
workspace/
├── .git/
├── backend/
│   ├── settings.gradle
│   ├── gradlew
│   ├── build.gradle
│   └── app/
│       └── build.gradle
└── scripts/
    └── inspect.ps1
```

### Trường hợp A: terminal đang ở repository root

PowerShell:

```powershell
Get-Location
git rev-parse --show-toplevel
Set-Location .\backend
.\gradlew.bat projects
```

Sau `Set-Location`, CWD là `workspace/backend/`, tức Gradle build root. Git vẫn nhận diện repository root là `workspace/`.

### Trường hợp B: terminal đang ở thư mục scripts

```powershell
Get-Location
git rev-parse --show-toplevel
..\backend\gradlew.bat -p ..\backend projects
```

Ở đây shell dùng đường dẫn `..\backend\gradlew.bat` để tìm Wrapper. Gradle nhận `..\backend` làm build root qua `-p`. CWD vẫn là `workspace/scripts/` trong suốt lệnh, trừ khi script hoặc tiến trình thay đổi working directory.

### Trường hợp C: build một subproject cụ thể

Từ `workspace/backend/`:

```powershell
.\gradlew.bat :app:build
```

`:app` là project path trong Gradle build, không phải đường dẫn tương đối của shell. Gradle tìm project `:app` theo cấu hình settings. Có thể project path và thư mục vật lý trùng cấu trúc tên, nhưng chúng là hai loại định danh khác nhau.

### Trường hợp D: ứng dụng cần đọc file tương đối

Nếu ứng dụng có file `backend/app/config/local.yml` và đọc đường dẫn `config/local.yml`, việc chạy từ `workspace/backend/app/` có thể tìm đúng file. Nhưng chạy cùng JAR từ `workspace/` sẽ khiến CWD khác và có thể không tìm thấy file đó. Hãy quyết định rõ file này là cấu hình triển khai bên ngoài, tài nguyên classpath hay dữ liệu nằm cạnh một thư mục triển khai, rồi chọn cơ chế nạp phù hợp.

## 10. Quy tắc thực hành để tránh nhầm lẫn

- Khi cần biết Git đang quản lý repository nào, dùng `git rev-parse --show-toplevel`.
- Khi cần biết shell đang đứng ở đâu, dùng `pwd` hoặc `Get-Location`.
- Khi cần biết Gradle build root, kiểm tra `settings.gradle` và dùng `-p/--project-dir` nếu muốn chỉ định rõ.
- Khi cần chọn Maven project, xác định POM và dùng `-f/--file` khi CWD không nằm ở thư mục chứa POM cần chạy.
- Khi cần biết ứng dụng Java đang phân giải đường dẫn tương đối từ đâu, in `System.getProperty("user.dir")` và đường dẫn tuyệt đối sau khi resolve.
- Khi cấu hình IDE hoặc CI, kiểm tra working directory riêng của từng Run Configuration/job step.
- Khi viết script, xác định rõ đường dẫn được tính từ CWD, từ vị trí script hay từ một tham số đầu vào; đừng trộn các mốc này.
- Khi repository chứa nhiều dự án, luôn chỉ rõ build/module cần thao tác thay vì mặc định repository root chính là build root.

Repository root trả lời câu hỏi “Git đang quản lý kho mã nào?”. Project/build root trả lời “công cụ build đang xử lý dự án hoặc build nào?”. Current working directory trả lời “tiến trình hiện tại đang đứng ở đâu để phân giải đường dẫn tương đối?”. Ba câu hỏi khác nhau nên có thể có ba câu trả lời khác nhau. Xác định đúng mốc trước khi chạy lệnh hoặc mở file sẽ giúp quy trình build, script, IDE và CI hoạt động nhất quán hơn.
