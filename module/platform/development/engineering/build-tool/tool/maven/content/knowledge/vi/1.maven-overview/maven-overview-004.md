# Vai trò của Maven so với JDK, IDE, Git và hệ thống CI

## 1. Bức tranh tổng thể

Khi xây dựng một ứng dụng Java, **JDK, Maven, IDE, Git và CI** giải quyết các vấn đề khác nhau nhưng phối hợp trong cùng một quy trình:

| Thành phần | Trách nhiệm chính | Ví dụ việc thường làm |
| --- | --- | --- |
| **JDK (Java Development Kit)** | Cung cấp công cụ và nền tảng để biên dịch, chạy, kiểm tra ứng dụng Java. | `javac` biên dịch mã nguồn; `java` chạy bytecode. |
| **Maven** | Tự động hóa quy trình build theo cấu hình dự án: quản lý phụ thuộc, gọi compiler, chạy các plugin và tạo artifact. | `mvn test`, `mvn package`, `mvn verify`. |
| **IDE** (IntelliJ IDEA, Eclipse, VS Code với Java extensions...) | Môi trường làm việc tương tác: viết mã, gợi ý, điều hướng, refactor, debug và chạy tác vụ. | Sửa `App.java`, đặt breakpoint, import dự án Maven. |
| **Git** | Quản lý phiên bản và lịch sử thay đổi của mã nguồn/cấu hình. | `git status`, `git commit`, `git push`. |
| **CI** (Continuous Integration) | Hệ thống tự động thực hiện quy trình kiểm tra/build khi có sự kiện như push hoặc pull request. | GitHub Actions/Jenkins chạy `mvn verify` trên máy CI. |

**Quan hệ cốt lõi:** JDK cung cấp năng lực biên dịch/chạy Java; Maven **điều phối** các công cụ và plugin theo một bản mô tả build; IDE giúp lập trình viên thao tác thuận tiện; Git lưu trữ và trao đổi phiên bản; CI gọi lại các bước build/kiểm tra trên môi trường tự động. Maven **không phải** ngôn ngữ Java, JDK, trình soạn thảo, hệ thống quản lý phiên bản hay máy chủ CI.

Một luồng điển hình:

~~~text
Lập trình viên dùng IDE để sửa Java và pom.xml
             |
             v
      JDK + Maven build/test trên máy cá nhân
             |
             v
       Git commit và push thay đổi
             |
             v
      CI checkout đúng phiên bản Git
             |
             v
  CI cài/cấu hình JDK rồi gọi Maven verify
             |
             v
   Kết quả kiểm tra và artifact (nếu cấu hình)
~~~

Trong luồng này, **Git kích hoạt hoặc cung cấp đầu vào** cho CI; **CI là bên điều phối lần chạy trên máy chủ**; **Maven là công cụ thực hiện build**; **JDK và các plugin thực hiện công việc Java cụ thể**.

## 2. Maven và JDK: ai biên dịch, ai điều phối?

JDK chứa các công cụ như `javac` và `java`. Một dự án Java rất nhỏ có thể biên dịch trực tiếp bằng `javac`. Khi dự án cần nhiều thư viện, nhiều module, quy tắc test, đóng gói, báo cáo và xuất bản artifact, việc duy trì chuỗi lệnh thủ công dễ sai lệch. Maven cung cấp mô hình thống nhất để điều phối các bước đó.

Maven đọc **`pom.xml` (Project Object Model)**, xác định cấu trúc dự án, tọa độ artifact, dependencies, plugin và lifecycle. Với phase `compile`, Maven gọi plugin biên dịch (thường là Maven Compiler Plugin); plugin sử dụng trình biên dịch Java tương ứng với cấu hình và JDK/toolchain khả dụng. Maven tự nó **không thay thế `javac`**.

Một số ranh giới quan trọng:

- `java -version` cho biết Java runtime mà lệnh `java` hiện tại sử dụng. `javac -version` cho biết phiên bản compiler trên `PATH`; chúng có thể khác Java mà Maven đang dùng.
- `mvn -version` cho biết phiên bản Maven và **Java runtime đang chạy Maven**. Khi gặp lỗi không tương thích JDK/plugin, đây là lệnh chẩn đoán đầu tiên.
- `<maven.compiler.release>17</maven.compiler.release>` yêu cầu compiler tương thích với API và bytecode của Java 17; **không cài JDK 17**. JDK dùng để biên dịch phải hỗ trợ mức release đó (hoặc được lựa chọn đúng qua Maven Toolchains).
- Maven có thể sử dụng Maven Toolchains để chọn JDK biên dịch khác với JDK dùng chạy Maven nếu dự án và máy đã cấu hình. Không mặc định đồng nhất JDK của IDE, terminal và CI.
- JDK và Maven đều cần được cài đặt/cấu hình phù hợp khi dự án không cung cấp một môi trường build đã đóng gói sẵn. Lần build đầu thường cần kết nối kho dependency/plugin để tải thành phần cần thiết.

**Ví dụ phân biệt:** `javac App.java` chủ yếu biên dịch tệp chỉ định; `mvn package` thực hiện các phase cần thiết trước `package` theo lifecycle, gọi plugin gắn vào các phase ấy, và tạo artifact theo loại đóng gói của dự án. Việc test thực sự có được chạy hay không còn phụ thuộc cấu hình plugin và các bài test hiện có.

## 3. Maven và IDE: cùng một dự án, hai cách thao tác

IDE cung cấp giao diện soạn thảo, autocomplete, debugger và khả năng chạy chương trình. Maven cung cấp **mô tả build có thể chia sẻ giữa các máy và công cụ**, chủ yếu thông qua `pom.xml`.

Khi mở dự án Maven, IDE thường đọc `pom.xml` để nhận biết các source root theo quy ước (`src/main/java`, `src/test/java`), dependencies, module và một phần cấu hình build. IDE có thể cung cấp nút chạy Maven goal/phase trong giao diện. Tuy nhiên nút **Build Project** của IDE không nhất thiết gọi toàn bộ lifecycle Maven; một IDE có thể dùng trình biên dịch và cơ chế build riêng để tăng tốc trong lúc phát triển.

Hệ quả thực tế:

1. Có thể **code chạy trong IDE nhưng `mvn verify` thất bại** vì IDE đang dùng JDK khác, môi trường khác hoặc bỏ qua bước plugin/test.
2. Có thể **Maven CLI chạy thành công nhưng IDE báo lỗi** vì chưa reload Maven project, chưa đồng bộ dependency hoặc cấu hình SDK trong IDE sai.
3. Để kiểm tra kết quả dự kiến sẽ chạy trên CI, hãy thực hiện **lệnh Maven trong terminal** bằng JDK phù hợp, thay vì chỉ dựa vào nút Run của IDE.

Cách phối hợp khuyên dùng: nhập dự án từ `pom.xml`; thống nhất phiên bản Java trong build; đồng bộ lại Maven sau khi sửa dependencies; dùng IDE để phát triển/debug và dùng `mvn verify` hoặc lệnh CI tương đương để kiểm tra trước khi gửi thay đổi.

## 4. Maven và Git: build khác với quản lý phiên bản

**Git trả lời “phiên bản nào, ai đổi gì, khi nào?”** Maven trả lời **“từ mã nguồn và cấu hình này, build và kiểm tra như thế nào?”**. Git không tự quản lý Maven dependencies hay bảo đảm commit biên dịch được; Maven không ghi lịch sử commit, merge branch hoặc thay Git.

Những tệp thường **được commit**: `pom.xml`, mã nguồn trong `src/`, các test, cấu hình CI, và Maven Wrapper (`mvnw`, `mvnw.cmd`, `.mvn/wrapper/`) nếu nhóm sử dụng. Những tệp **thường không commit**: kết quả build `target/`, các tệp `*.class` phát sinh và metadata IDE chỉ dành cho máy cá nhân (tùy quy ước nhóm). Thư mục cache Maven như `~/.m2/repository` thường nằm ngoài repository Git.

Ví dụ `.gitignore` tối thiểu:

~~~gitignore
# Kết quả Maven tạo ra
target/

# File class biên dịch thủ công
*.class

# Cấu hình IDE chỉ dành cho máy cá nhân (tùy chính sách nhóm)
.idea/
~~~

`git add` và `git commit` lưu lại các thay đổi đã chọn; `git push` gửi commit lên remote. Một commit thành công **không chứng minh** build/test đạt. Kiểm tra bằng Maven trước push và trên CI giúp phát hiện lỗi sớm hơn.

Maven có thể tích hợp thông tin từ Git qua plugin được cấu hình riêng, nhưng **Maven không tự commit/push** chỉ vì chạy `package` hoặc `verify`.

## 5. Maven và CI: Maven là công cụ build bên trong pipeline

CI như GitHub Actions, GitLab CI hoặc Jenkins cung cấp môi trường, quyền truy cập mã nguồn, lịch kích hoạt, secret, log và trạng thái job. Pipeline thường:

1. Nhận sự kiện push/pull request.
2. Checkout một commit cụ thể từ Git.
3. Thiết lập JDK và môi trường (biến môi trường, cache, credentials khi cần).
4. Chạy lệnh Maven giống quy trình được nhóm thống nhất.
5. Báo trạng thái pass/fail; tùy cấu hình có thể lưu báo cáo test và artifact hoặc tiếp tục đến bước phát hành.

Maven phụ trách các phase như `validate`, `compile`, `test`, `package`, `verify`; CI phụ trách **khi nào, ở đâu, với quyền gì và xử lý kết quả ra sao**. `mvn verify` đi qua các phase trước nó của default lifecycle và chạy các plugin goal được gắn vào đó. Nó **không tự bảo đảm** có integration test, security scan, deploy hay release nếu các bước/plugin liên quan chưa được cấu hình.

Ví dụ workflow GitHub Actions tại `.github/workflows/java-ci.yml`:

~~~yaml
name: Java CI
on:
  push:
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven
      - name: Build and verify
        run: mvn -B -ntp clean verify
~~~

Giải thích: `checkout` lấy mã nguồn; `setup-java` thiết lập JDK 17; Maven chạy build/test theo POM. `-B` chọn batch mode phù hợp CI; `-ntp` ẩn thanh tiến độ tải xuống khỏi log. Nếu dự án dùng **Maven Wrapper**, CI có thể gọi `./mvnw -B -ntp clean verify` sau khi bảo đảm script có quyền thực thi; wrapper giúp chọn phiên bản Maven đã quy định cho dự án. CI vẫn phải cung cấp JDK tương thích.

Không đưa mật khẩu/token trực tiếp vào `pom.xml` hoặc workflow đã commit. Khi cần truy cập kho private hay xuất bản artifact, dùng cơ chế secret và cấu hình phù hợp của CI/Maven. Cache dependency giúp nhanh hơn nhưng **không thay thế** việc khai báo dependency đúng phiên bản.

## 6. Ví dụ Java 17 có thể chạy: JDK thực thi, Maven đóng gói, Git lưu vết, CI kiểm tra

Giả sử dự án có cấu trúc:

~~~text
maven-role-demo/
├── pom.xml
├── .gitignore
└── src/
    └── main/
        └── java/
            └── org/
                └── example/
                    └── App.java
~~~

Nội dung `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>org.example</groupId>
    <artifactId>maven-role-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nội dung `src/main/java/org/example/App.java`:

~~~java
package org.example;

public final class App {
    public static void main(String[] args) {
        System.out.println("Xin chào từ Maven!");
    }
}
~~~

**Lựa chọn A — dùng JDK trực tiếp** (chạy ở thư mục gốc dự án):

~~~bash
javac -encoding UTF-8 -d out src/main/java/org/example/App.java
java -cp out org.example.App
~~~

Kết quả của lệnh `java`:

~~~text
Xin chào từ Maven!
~~~

Ở đây `javac` tạo `out/org/example/App.class`; `java` chạy class đó. Không có Maven tham gia. Trên một dự án có thư viện bên ngoài, cách này sẽ cần tự xử lý classpath và nhiều tác vụ khác.

**Lựa chọn B — dùng Maven** (cần Maven và JDK tương thích; lần chạy đầu có thể tải plugin):

~~~bash
mvn -version
mvn -B -ntp clean package
java -cp target/maven-role-demo-1.0.0.jar org.example.App
~~~

Kết quả của lệnh chạy class:

~~~text
Xin chào từ Maven!
~~~

Maven đọc POM, chạy các bước mặc định của lifecycle và tạo `target/maven-role-demo-1.0.0.jar` khi build thành công. JAR này **không được khai báo `Main-Class` trong manifest**, vì vậy cách chạy đúng cho ví dụ là `java -cp ... org.example.App`, không giả định `java -jar ...` sẽ hoạt động.

**Lựa chọn C — đưa cùng một dự án vào quy trình nhóm:** commit `pom.xml`, `src/`, `.gitignore`, và workflow CI (nếu có); push lên remote. CI checkout commit đó, thiết lập JDK rồi chạy `mvn -B -ntp clean verify`. Vì ví dụ chưa có mã kiểm thử, phase test sẽ không cung cấp bằng chứng đã kiểm thử hành vi; trong dự án thực, hãy bổ sung test và cấu hình cần thiết.

## 7. Phân biệt các lệnh dễ nhầm

| Lệnh/thao tác | Chủ thể | Ý nghĩa thực tế |
| --- | --- | --- |
| `javac ...` | JDK | Biên dịch mã nguồn Java, với nguồn/classpath chỉ định. |
| `java ...` | Java runtime thuộc bộ công cụ Java | Chạy class hoặc chương trình đã đóng gói đúng cách. |
| `mvn compile` | Maven + compiler plugin/JDK | Chạy lifecycle đến phase `compile`. |
| `mvn test` | Maven + plugin/test framework | Chạy đến phase `test`; chỉ kiểm tra những test thực sự hiện có và được cấu hình. |
| `mvn package` | Maven + các plugin | Chạy đến `package`, tạo artifact theo cấu hình dự án. |
| `mvn verify` | Maven + các plugin | Chạy đến `verify`, gồm các kiểm tra được gắn vào lifecycle. |
| Nút Run/Debug trong IDE | IDE (có thể dùng JDK/Maven) | Chạy/debug từ giao diện, không mặc nhiên giống đầy đủ quy trình Maven trên CI. |
| `git commit` | Git | Ghi snapshot phiên bản vào lịch sử Git cục bộ. |
| CI job gọi `mvn verify` | CI điều phối; Maven thực thi | Build/kiểm tra một commit trên runner theo pipeline. |

Lưu ý: Maven có các lifecycle khác nhau như `clean`, `default`, `site`. `mvn clean verify` chạy yêu cầu `clean` và sau đó lifecycle tới `verify`; không nên hiểu `clean` là phase đứng ngay trước `compile` trong cùng một lifecycle.

## 8. Lỗi thường gặp và cách xác định đúng công cụ chịu trách nhiệm

- **“Chạy được trong IDE nhưng CI báo `invalid target release`.”** Kiểm tra JDK thực tế bằng `mvn -version` trên runner, cấu hình Java release và toolchains. IDE có thể đang dùng JDK mới hơn.
- **“Maven không tìm thấy thư viện hoặc plugin.”** Kiểm tra dependency coordinates, repositories, kết nối mạng/proxy, cấu hình `settings.xml` và quyền truy cập kho. Git commit không tự mang về toàn bộ dependency cache.
- **“Vừa đổi `pom.xml` mà IDE vẫn báo lỗi import.”** Reload/reimport Maven project; kiểm tra Maven JVM, Project SDK và trạng thái tải dependencies.
- **“`git push` thành công nhưng pipeline đỏ.”** Git đã làm đúng chức năng truyền commit; đọc log job để xác định lỗi setup JDK, tải dependency, compile, test hoặc plugin.
- **“`mvn package` thành công nên ứng dụng chắc chắn chạy được.”** Package thành công chỉ xác nhận những bước build/plugin đã thực thi; vẫn có thể thiếu cấu hình runtime, main manifest, test hoặc kiểm tra tích hợp.
- **“Máy A build được, máy B/CI thất bại.”** So sánh JDK, Maven/Wrapper, profiles, settings, biến môi trường, dependency/plugin version và dịch vụ bên ngoài. Để tăng khả năng lặp lại, thống nhất phiên bản toolchain và khai báo rõ phiên bản plugin/phụ thuộc quan trọng.

## 9. Ghi nhớ và tự kiểm tra

Khi chọn công cụ, hãy tự hỏi: **Tôi cần biên dịch/chạy Java?** → JDK. **Tôi cần build, quản lý dependency và đóng gói theo một cấu hình chung?** → Maven. **Tôi cần viết/debug mã dễ dàng?** → IDE. **Tôi cần lưu lịch sử, nhánh và trao đổi thay đổi?** → Git. **Tôi cần kiểm tra tự động mỗi khi nhóm gửi code?** → CI phối hợp với Git, JDK và Maven.

Ba tình huống để tự đánh giá:

1. Đã commit nhưng quên chạy test: **Git không thay Maven hoặc CI**; thêm bước `mvn verify` vào quy trình kiểm tra.
2. IDE báo xanh nhưng pipeline fail: đối chiếu **JDK/Maven và lệnh build thực tế** trên IDE, terminal và CI.
3. Muốn mọi thành viên build cùng cách: commit **POM, source, test**, cân nhắc **Maven Wrapper**, thống nhất JDK và chạy cùng lệnh Maven ở máy cá nhân lẫn CI.

**Kết luận:** Maven là điểm chung để mô tả và thực thi quá trình build của dự án Java. JDK cung cấp công cụ Java; IDE tối ưu thao tác phát triển; Git quản lý phiên bản; CI tự động gọi lại quy trình đó. Hiểu đúng ranh giới giúp chọn công cụ để xử lý lỗi, xây dựng pipeline đáng tin cậy và tránh tình trạng “chỉ chạy trên máy tôi”.