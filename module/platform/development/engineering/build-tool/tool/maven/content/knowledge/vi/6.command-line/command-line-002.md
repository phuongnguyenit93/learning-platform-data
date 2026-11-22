# Chạy Maven từ đúng thư mục và chỉ định POM bằng `-f`

## 1. Bài toán: một lệnh Maven có thể chọn nhầm dự án

Maven cần biết **`pom.xml` nào** mô tả project đang được build. Theo mặc định, nếu bạn chạy `mvn clean verify` trong thư mục có `pom.xml`, Maven sử dụng POM đó. Nếu đang đứng tại thư mục khác, một lệnh trông giống hệt có thể không tìm thấy project hoặc chọn POM của project khác.

Ví dụ:

```text
workspace/
├── service-a/
│   ├── pom.xml
│   └── src/main/java/...
├── service-b/
│   ├── pom.xml
│   └── src/main/java/...
└── notes/
    └── README.md
```

- Ở `workspace/service-a`, `mvn package` build `service-a`.
- Ở `workspace/service-b`, `mvn package` build `service-b`.
- Ở `workspace/notes`, `mvn package` thường lỗi vì không có `pom.xml`.
- Ở `workspace`, Maven cũng không tự dò tất cả thư mục con; muốn build module nào cần chọn project hoặc POM tổng hợp thích hợp.

Câu hỏi cần trả lời trước khi chẩn đoán bất kỳ lỗi Maven nào: **terminal đang ở đâu, POM nào đã được chọn và mục tiêu build là gì?**

## 2. Phân biệt ba khái niệm về đường dẫn

| Khái niệm | Nghĩa | Ví dụ khi shell ở `workspace` |
| --- | --- | --- |
| Shell working directory (CWD) | Thư mục terminal hiện tại | `workspace/` |
| POM được chọn | Tệp Maven đọc để hiểu dự án | `workspace/service-a/pom.xml` |
| Project basedir | Thư mục gốc của project chứa POM | `workspace/service-a/` |

Nếu chạy `mvn -f service-a/pom.xml package` từ `workspace` thì **shell vẫn ở `workspace`**, nhưng Maven chọn POM và project basedir của `service-a`.

Đầu ra Maven mặc định được đặt tương đối so với project basedir: source tại `src/main/java`, test tại `src/test/java` và output tại `target` bên dưới project. Vì vậy sau build, file JAR có thể ở `workspace/service-a/target` chứ không phải `workspace/target`.

Trong POM, biểu thức `${project.basedir}` đại diện cho basedir của project đang được xử lý; `${project.build.directory}` thường trỏ tới `target` của project đó. Đừng nhầm hai biến này với CWD của shell.

**Ngoại lệ cần lưu ý:** script tùy chỉnh hoặc plugin có cấu hình working directory riêng có thể diễn giải một số đường dẫn theo cơ chế khác. Khi gặp lỗi path trong plugin, đọc tài liệu và cấu hình của **chính plugin đó**.

## 3. Cách truyền thống: `cd` vào thư mục chứa `pom.xml`

Từ một terminal ở `workspace`:

```bash
cd service-a
mvn clean verify
```

Trên Windows PowerShell:

```powershell
Set-Location .\service-a
mvn clean verify
```

Kiểm tra thư mục hiện tại bằng `pwd` (Bash) hoặc `Get-Location` (PowerShell). Có thể dùng `ls pom.xml` ở Bash hoặc `Get-ChildItem pom.xml` ở PowerShell để xác nhận tệp POM ở thư mục đang đứng.

Mẹo: `mvn -version` chỉ cho biết phiên bản Maven và JDK mà Maven đang dùng; nó **không xác nhận** Maven đang chọn đúng POM. Hãy quan sát vị trí POM hoặc chỉ định POM tường minh.

Dùng `cd` rất rõ ràng khi bạn làm việc trong một project. Tuy nhiên, đối với script CI hoặc công cụ build khởi chạy từ monorepo root, truyền đường dẫn POM bằng `-f` thường tiện hơn.

## 4. `-f` và `--file`: chọn project mà không đổi thư mục shell

Maven CLI cung cấp cú pháp:

```text
-f, --file <đường-dẫn-POM-hoặc-thư-mục-chứa-POM>
```

Từ `workspace`, các lệnh sau chọn cùng project nếu `service-a/pom.xml` tồn tại:

```bash
mvn -f service-a/pom.xml clean verify
mvn --file service-a/pom.xml clean verify
mvn -f service-a clean verify
```

Option `-f` cho Maven biết **đọc POM nào**; phần `clean verify` cho Maven biết **thực hiện việc gì**. `-f` không tự chuyển sang phase `verify`, cũng không tự tải package hay thay đổi tên artifact.

Một số lệnh minh họa:

| Lệnh | Ý nghĩa |
| --- | --- |
| `mvn -f service-a/pom.xml validate` | Đọc POM đã chọn và chạy default lifecycle đến validate |
| `mvn -f service-a/pom.xml test` | Đến phase test của project đã chọn |
| `mvn -f service-a/pom.xml package` | Biên dịch/test/đóng gói theo plugin binding |
| `mvn -f service-a/pom.xml clean verify` | Clean lifecycle rồi default lifecycle đến verify |
| `mvn -f service-a/pom.xml dependency:tree` | Gọi goal của Maven Dependency Plugin trên project đã chọn |
| `mvn -f service-a/pom.xml help:effective-pom` | In effective POM của project đã chọn |

**Thứ tự dễ đọc:** `mvn -f đường/dẫn/pom.xml <phase-hoặc-goal>`. Đừng đưa đường dẫn POM vào tên goal hoặc nhầm `-f` với `-D` (khai property), `-o` (offline) hay `-pl` (chọn các module trong reactor).

### Đường dẫn tương đối

Đường dẫn sau `-f` được diễn giải dựa trên **thư mục lúc gọi Maven**. Giả sử đang ở `workspace`:

```bash
mvn -f service-a/pom.xml verify
```

Nếu đang ở `workspace/service-a/src` thì phải thay bằng:

```bash
mvn -f ../pom.xml verify
```

Không thể giữ nguyên `-f service-a/pom.xml` trong mọi CWD rồi kỳ vọng Maven luôn tìm được cùng file. Đây là nguyên nhân phổ biến của lỗi `Non-readable POM`.

### Đường dẫn tuyệt đối và khoảng trắng

Đường dẫn tuyệt đối không phụ thuộc CWD. Ví dụ Bash:

```bash
mvn -f /opt/workspace/service-a/pom.xml clean verify
```

Ví dụ PowerShell:

```powershell
mvn -f 'C:\work\workspace\service-a\pom.xml' clean verify
```

Đặt đường dẫn có dấu cách trong dấu nháy:

```bash
mvn -f "projects/My Java App/pom.xml" clean verify
```

```powershell
mvn -f 'C:\work\My Java App\pom.xml' clean verify
```

Không nhét `-f` và đường dẫn vào cùng một chuỗi được quote; Maven cần nhận option và giá trị của option hợp lệ.

## 5. Ví dụ Java 17 có thể build từ bên ngoài thư mục dự án

Tạo cấu trúc:

```text
workspace/
└── hello-maven/
    ├── pom.xml
    └── src/main/java/demo/Hello.java
```

File `workspace/hello-maven/pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `workspace/hello-maven/src/main/java/demo/Hello.java`:

```java
package demo;

public final class Hello {
    private Hello() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Maven -f");
    }
}
```

Cần JDK 17+, Maven và quyền tải plugin khi cache chưa có. Đứng tại `workspace`, chạy:

```bash
mvn -version
mvn -f hello-maven/pom.xml clean package
java -cp hello-maven/target/hello-maven-1.0.0.jar demo.Hello
```

Khi build thành công, **stdout chính xác của chương trình Java** là:

```text
Hello from Maven -f
```

Còn từ `workspace/hello-maven`, các lệnh tương đương:

```bash
mvn clean package
java -cp target/hello-maven-1.0.0.jar demo.Hello
```

Lệnh `java -cp` chạy class `demo.Hello` vì JAR thông thường của ví dụ chưa có `Main-Class` trong manifest. `mvn package` chỉ đóng gói; nó không tự khởi động chương trình Java.

Kiểm tra chính xác output:

```text
workspace/hello-maven/target/
├── classes/demo/Hello.class
└── hello-maven-1.0.0.jar
```

Các file metadata/plugin khác có thể cùng xuất hiện trong `target`. Nếu sau khi gọi Maven từ `workspace` bạn tìm nhầm `workspace/target/hello-maven-1.0.0.jar`, có thể tưởng build không tạo file, dù artifact thực sự đã được ghi vào project basedir.

## 6. Dự án nhiều module: `-f`, `-pl` và `-am`

Giả sử có một POM tổng hợp:

```text
workspace/shop/
├── pom.xml
├── core/
│   └── pom.xml
└── app/
    └── pom.xml
```

POM `shop/pom.xml` thường dùng `<packaging>pom</packaging>` và khai các `<modules>`. Từ `workspace`:

```bash
mvn -f shop/pom.xml clean verify
```

Maven tạo **reactor** từ root aggregator, xét các module được khai và dependency giữa chúng.

Nếu chỉ muốn build `app` và những module trong reactor cần cho `app`:

```bash
mvn -f shop/pom.xml -pl app -am verify
```

Ở đây `-f` chọn **root POM**, `-pl` (`--projects`) chọn **module trong reactor**, `-am` (`--also-make`) thêm các module mà module được chọn phụ thuộc.

Cần phân biệt với:

```bash
mvn -f shop/app/pom.xml verify
```

Lệnh thứ hai chọn **POM của app** trực tiếp, nên không tự xây module `core` ở bên cạnh. Nếu `app` phụ thuộc artifact `core` chưa có trong local/remote repository, build có thể không resolve được dependency. Lúc này chọn root POM với `-pl app -am` thường phù hợp hơn nếu POM tổng hợp có chứa các module đó.

**Parent POM và aggregator POM không phải cùng một quan hệ.** `<parent>` thiết lập inheritance của cấu hình; `<modules>` thiết lập aggregation. Một POM có thể làm cả hai, nhưng chỉ thừa kế parent không tự đưa mọi sibling module vào reactor.

### Maven Wrapper

Nếu project cung cấp `mvnw`/`mvnw.cmd`, đó là công cụ giúp dùng phiên bản Maven theo cấu hình của dự án. Wrapper và `-f` giải quyết hai việc khác nhau: **chọn Maven executable** và **chọn POM**. Ví dụ từ project root:

```bash
./mvnw clean verify
```

PowerShell:

```powershell
.\mvnw.cmd clean verify
```

Không suy luận rằng dùng `mvn -f ...` sẽ tự kích hoạt Maven Wrapper; lệnh `mvn` sử dụng Maven mà shell tìm thấy trong `PATH`.

## 7. Thư mục của plugin/script có thể gây bất ngờ

Các đường dẫn theo property của Maven như:

```xml
<configuration>
    <inputDirectory>${project.basedir}/specs</inputDirectory>
    <outputDirectory>${project.build.directory}/generated</outputDirectory>
</configuration>
```

là **phần cấu hình minh họa** cho plugin có các tham số phù hợp, không phải cấu hình POM độc lập. Chúng biểu thị rõ việc căn đường dẫn theo project.

Nếu plugin gọi process bên ngoài hoặc cho phép cấu hình working directory riêng, CWD của process đó có thể khác project basedir. Đọc tài liệu plugin thay vì tự giả định. Tránh đặt đường dẫn tuyệt đối như `C:\Users\someone\Desktop\output` trong POM dùng chung vì đồng đội/CI không có đường dẫn ấy.

Với CI, hai chiến lược phổ biến là:

1. Đặt step working directory tới thư mục có `pom.xml`, sau đó chạy `mvn clean verify`.
2. Giữ CI tại workspace root và gọi `mvn -f project/pom.xml clean verify`.

Để ổn định khi script được gọi từ nhiều vị trí, nên xác định đường dẫn POM tuyệt đối từ workspace root hoặc vị trí chính script rồi truyền nó với `-f`. Điều này giảm phụ thuộc vào thói quen mở terminal của người chạy build.

## 8. Chẩn đoán lỗi do sai POM hoặc sai thư mục

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `The goal you specified requires a project ... but there is no POM` | Đang đứng ở thư mục không chứa POM | Xác định `pwd`/`Get-Location`, chuyển tới root hoặc dùng `-f` |
| `Non-readable POM` hoặc `The specified file does not exist` | Sai path, thiếu quote, không có quyền đọc | Kiểm tra path từ CWD, xác nhận tồn tại, quote đường dẫn |
| Build xong nhưng không thấy JAR | Tìm nhầm `target` theo CWD | Kiểm tra `${project.basedir}/target` |
| Build nhầm ứng dụng | Có nhiều POM và chọn sai project | Dùng `-f` chính xác, xem tên project/version trong Maven log |
| Module con không tìm được artifact của module khác | Chạy module riêng khi dependency nội bộ chưa cài | Dùng root aggregator + `-pl`/`-am` nếu có reactor phù hợp |
| IDE build được nhưng terminal fail | IDE và terminal chọn POM, JDK, profile, Maven version khác | So sánh project root, `mvn -version`, effective POM và options |
| Script có relative path sai | Script/plugin dùng working directory khác dự đoán | Xác định basedir và working directory của plugin/script |

Để kiểm tra path trên Bash:

```bash
pwd
ls service-a/pom.xml
mvn -f service-a/pom.xml validate
```

Trên PowerShell:

```powershell
Get-Location
Test-Path .\service-a\pom.xml
mvn -f '.\service-a\pom.xml' validate
```

`validate` giúp xác nhận Maven có thể đọc project và chạy giai đoạn đầu, **không đảm bảo** compiler/test/package sẽ thành công.

Nếu cần xem cấu hình thực tế sau inheritance, thử `mvn -f service-a/pom.xml help:effective-pom`. Nếu nghi có nhiều modules, xem POM aggregator và các `<modules>` thực tế trước khi dùng `-pl`.

## 9. Checklist và câu hỏi tự kiểm tra

- [ ] Shell đang đứng ở đâu?
- [ ] POM tôi định build ở đường dẫn chính xác nào?
- [ ] Dùng `-f` tương đối có đúng từ CWD hiện tại không?
- [ ] Đường dẫn có dấu cách đã được quote đúng chưa?
- [ ] Maven đang dùng đúng JDK và Maven executable chưa?
- [ ] Tôi muốn build một project độc lập hay reactor nhiều module?
- [ ] Tôi đã chọn phase/goal phù hợp: `test`, `verify`, `package`, `dependency:tree`... chưa?
- [ ] Tôi tìm output tại `target` của đúng project chưa?
- [ ] Script hoặc plugin có working directory riêng cần cấu hình không?

**Tự kiểm tra:** nếu shell ở `workspace`, project ở `workspace/service-a` và lệnh là `mvn -f service-a/pom.xml package`, Maven đọc POM nào và tạo output ở đâu? **Đáp án:** Maven đọc `workspace/service-a/pom.xml`; theo cấu hình mặc định, output ở `workspace/service-a/target`. Shell không đổi thư mục sau khi Maven chạy.

**Ghi nhớ:** `cd` thay đổi thư mục của **terminal**; `-f` chọn **POM của Maven**; `-pl` chọn module trong **reactor**; `-am` kéo theo các reactor dependency cần build. Nắm rõ bốn việc ấy giúp tránh phần lớn lỗi “chạy Maven từ nhầm chỗ”.

## Tham khảo

- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/current/maven-embedder/cli.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
