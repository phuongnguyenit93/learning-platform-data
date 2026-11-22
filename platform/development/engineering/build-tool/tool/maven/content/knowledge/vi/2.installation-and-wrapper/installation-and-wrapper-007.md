# Chạy mvnw hoặc mvnw.cmd nhất quán giữa các môi trường

## 1. Mục tiêu và ý nghĩa

Trong một dự án Maven, **Maven Wrapper** cung cấp hai điểm vào để chạy cùng một phiên bản Maven đã chọn cho dự án:

- **mvnw**: script dành cho shell tương thích POSIX, thường dùng trên Linux và macOS; cũng dùng được trong Git Bash nếu môi trường đáp ứng yêu cầu.
- **mvnw.cmd**: script batch dành cho Windows, chạy từ Command Prompt (cmd.exe) hoặc được PowerShell gọi như một chương trình bên ngoài.

Khi repository đã chứa Wrapper, các thành viên và hệ thống CI gọi script tương ứng với hệ điều hành, thay vì phụ thuộc vào phiên bản Maven toàn cục từ lệnh **mvn**. Cả hai script đọc cấu hình Wrapper của **cùng dự án** để tải (khi cần) và chạy bản phân phối Maven đã chỉ định.

**Kết quả mong muốn:** một câu lệnh build về mặt ý nghĩa (**clean verify**, **package**, **test**...) được thực thi bằng **cùng phiên bản Maven** trên máy phát triển và CI, mặc dù tên script và cách ghi đường dẫn khác nhau theo hệ điều hành.

Wrapper **không tự cài JDK**, không đóng băng hệ điều hành hoặc toàn bộ dependency và không đảm bảo mọi kết quả build giống nhau nếu Java, profile, plugin, biến môi trường hay cấu hình khác nhau. Ta phải kiểm soát những yếu tố đó riêng.

## 2. Các tệp cần có trong repository

Cấu trúc thường gặp:

~~~text
wrapper-demo/
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    ├── main/
    │   └── java/
    └── test/
        └── java/
~~~

Tệp **.mvn/wrapper/maven-wrapper.properties** chứa **distributionUrl** trỏ đến bản phân phối Maven của dự án. Ví dụ một URL cho Maven 3.9.9:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

URL trên chỉ là ví dụ về **một phiên bản được cố định**; dự án thực tế chọn phiên bản đáp ứng yêu cầu kỹ thuật và chính sách nâng cấp của nhóm. Cần commit cả script lẫn tệp properties để người khác dùng chính xác cấu hình đó.

Tùy **kiểu Wrapper**, thư mục .mvn/wrapper/ có thể chứa thêm **maven-wrapper.jar** hoặc **MavenWrapperDownloader.java**. Với kiểu **only-script** của Apache Maven Wrapper hiện đại, hai script có thể trực tiếp tải Maven, nên **không có JAR wrapper** là điều bình thường. Không tự kết luận bộ Wrapper bị thiếu chỉ vì không thấy tệp JAR.

Khi Maven chưa có trong bộ nhớ đệm Wrapper, lần chạy đầu tải và giải nén bản phân phối theo **distributionUrl**, thường lưu dưới thư mục **~/.m2/wrapper/dists** (hoặc vị trí do cấu hình môi trường quyết định). Các lần sau thường tái sử dụng bản đã tải. Việc tải Maven và việc tải dependency/plugin từ repository Maven là hai hoạt động khác nhau.

## 3. Câu lệnh chuẩn trên từng hệ điều hành

**Đứng tại thư mục gốc repository** (nơi có pom.xml, mvnw và mvnw.cmd) trước khi chạy.

| Môi trường | Kiểm tra Maven Wrapper đang chạy | Build có kiểm thử theo các pha đã cấu hình |
| --- | --- | --- |
| Linux, macOS (Bash, sh, zsh) | **./mvnw --version** | **./mvnw -B -ntp clean verify** |
| Windows PowerShell | **.\mvnw.cmd --version** | **.\mvnw.cmd -B -ntp clean verify** |
| Windows Command Prompt (cmd.exe) | **mvnw.cmd --version** | **mvnw.cmd -B -ntp clean verify** |
| Windows Git Bash | **./mvnw --version** | **./mvnw -B -ntp clean verify** |

**Tại sao khác cú pháp?**

- **./** trên hệ POSIX chỉ tệp thực thi **mvnw** trong thư mục hiện tại. Script cần quyền thực thi; shell tương thích POSIX phải có sẵn.
- **.\** trong PowerShell chỉ tệp **mvnw.cmd** ở thư mục hiện tại; PowerShell mặc định không tìm chương trình trong thư mục hiện tại nếu chỉ nhập tên trần.
- **cmd.exe** tìm lệnh trong thư mục hiện tại, vì vậy có thể gọi **mvnw.cmd**. Cách viết **.\mvnw.cmd** cũng có thể dùng khi muốn tường minh.
- **Git Bash trên Windows** có môi trường shell kiểu POSIX nên thường chạy được **./mvnw**; với PowerShell hoặc cmd.exe, sử dụng **mvnw.cmd** là lựa chọn rõ ràng.

Các tham số sau tên script là **tham số Maven**:

- **--version** (hoặc **-v**) hiển thị phiên bản Maven và Java mà quá trình build thực sự sử dụng.
- **-B** bật batch mode, phù hợp CI và log không tương tác.
- **-ntp** tắt tiến độ truyền tải, giúp log gọn hơn; tính năng này có trong Maven 3.9.9 ở ví dụ.
- **clean verify** yêu cầu dọn kết quả build rồi chạy các pha của lifecycle default đến **verify**. Test chỉ được chạy khi dự án có test hợp lệ và plugin/thiết lập nhận diện chúng.

Các ví dụ dưới đây là **những lệnh tương đương**, không cần thực hiện tất cả trên một máy.

**Linux/macOS — terminal:**

~~~bash
cd /duong-dan/den/wrapper-demo
./mvnw --version
./mvnw -B -ntp clean verify
~~~

**Windows PowerShell — terminal:**

~~~powershell
cd C:\du-an\wrapper-demo
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp clean verify
~~~

**Windows Command Prompt — terminal:**

~~~bat
cd /d C:\du-an\wrapper-demo
mvnw.cmd --version
mvnw.cmd -B -ntp clean verify
~~~

Đường dẫn **/duong-dan/den/wrapper-demo** và **C:\du-an\wrapper-demo** ở trên là ví dụ về vị trí thư mục: thay bằng thư mục repository thực tế.

## 4. Wrapper vận hành như thế nào?

~~~text
Người phát triển hoặc CI
          |
          | gọi ./mvnw hoặc .\mvnw.cmd
          v
Script Wrapper của repository
          |
          | đọc .mvn/wrapper/maven-wrapper.properties
          v
Phân phối Maven đã cố định phiên bản
          |
          | nếu chưa có: tải và giải nén vào bộ đệm
          v
Maven thực thi các mục tiêu được truyền vào
          |
          +--> đọc pom.xml và settings hiệu lực
          +--> giải quyết dependency/plugin
          +--> chạy lifecycle / goal tương ứng
          v
Kết quả build và mã thoát của tiến trình
~~~

Ví dụ, trên Linux lệnh:

~~~bash
./mvnw -B -ntp clean verify
~~~

và trên Windows PowerShell lệnh:

~~~powershell
.\mvnw.cmd -B -ntp clean verify
~~~

cùng truyền **-B -ntp clean verify** đến Maven. Cách gọi script khác nhau để phù hợp shell; yêu cầu build và **distributionUrl** là chung.

**Kiểm tra thực tế:** chạy lệnh **--version** trên mỗi môi trường. Đối chiếu dòng **Apache Maven** với phiên bản cố định trong properties và dòng **Java version** với phiên bản Java dự án yêu cầu. Đừng chỉ kiểm tra **mvn --version**, vì đó có thể là bản Maven cài riêng trên máy.

## 5. Ví dụ thực hành từ một dự án Java 17

Ví dụ này cho thấy một dự án Maven nhỏ có thể được build bằng Wrapper trên cả Windows lẫn Linux/macOS. Các tệp Java và POM dưới đây là **nội dung đầy đủ có thể dùng để thực hành**; các script Wrapper được **Maven Wrapper Plugin sinh ra**, không tự viết tay.

**Bước 1 — tạo pom.xml:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>wrapper-demo</artifactId>
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

Ở đây **maven.compiler.release=17** yêu cầu Java bytecode/API tương thích Java 17. Máy build cần một JDK hỗ trợ mục tiêu release này. Đã cố định phiên bản Maven Compiler Plugin để tránh phụ thuộc hoàn toàn vào plugin mặc định của một môi trường.

**Bước 2 — tạo src/main/java/vn/example/HelloWrapper.java:**

~~~java
package vn.example;

public final class HelloWrapper {
    private HelloWrapper() {
    }

    public static void main(String[] args) {
        System.out.println("Xin chào từ Maven Wrapper!");
    }
}
~~~

**Bước 3 — người chuẩn bị dự án tạo Wrapper một lần.** Nếu dự án chưa có Wrapper, người duy trì cần Maven cài sẵn để chạy mục tiêu tạo script. Ví dụ lệnh trên terminal POSIX:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9 -Dtype=only-script
~~~

Lệnh này cài các tệp Wrapper và chọn Maven **3.9.9** làm phiên bản phân phối. Nếu dự án **đã có Wrapper**, bỏ qua bước tạo; đừng tái tạo ở mỗi lần build. Commit các tệp được sinh ra để đồng đội không phải cài Maven toàn cục. Đối với Windows PowerShell khi thực hiện bước chuẩn bị, có thể đặt đối số dạng **"-Dmaven=3.9.9"** trong dấu nháy nếu cần để shell truyền nguyên vẹn.

**Bước 4 — chạy bằng Wrapper:**

~~~bash
# Linux/macOS hoặc Git Bash
./mvnw --version
./mvnw -B -ntp clean verify
java -cp target/wrapper-demo-1.0.0.jar vn.example.HelloWrapper
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp clean verify
java -cp target\wrapper-demo-1.0.0.jar vn.example.HelloWrapper
~~~

Lệnh **verify** chạy build và tạo JAR ở pha package của packaging **jar**; ví dụ **không tạo bài kiểm thử**, nên không nên diễn giải log “BUILD SUCCESS” thành bằng chứng đã có test chạy. Lệnh **java -cp ...** chạy lớp main từ JAR. **Đầu ra chính xác của riêng lệnh Java cuối cùng**:

~~~text
Xin chào từ Maven Wrapper!
~~~

Đây là JAR thông thường, chưa gắn **Main-Class** trong manifest, nên dùng **java -cp ... tên.package.Lớp**. Chạy **java -jar** sẽ cần cấu hình manifest phù hợp. Hai nền tảng sinh cùng tên artifact theo POM là **target/wrapper-demo-1.0.0.jar**, nhưng byte của artifact không nhất thiết luôn trùng nếu có yếu tố build không tái lập.

## 6. Quyền thực thi và việc lưu Wrapper vào Git

Trên Linux/macOS, nếu gặp **Permission denied** khi gọi **./mvnw**, kiểm tra quyền thực thi của script:

~~~bash
chmod +x mvnw
./mvnw --version
~~~

Để bảo toàn quyền thực thi khi checkout sang máy khác, đưa bit executable của **mvnw** vào Git index:

~~~bash
git add mvnw mvnw.cmd .mvn/wrapper/
git update-index --chmod=+x mvnw
git diff --cached --summary
~~~

Git sẽ lưu quyền executable cho script POSIX. Trên Windows, việc thay đổi file mode có thể không được phát hiện tự động, nên **git update-index --chmod=+x mvnw** giúp đặt rõ bit này trong index. Kiểm tra diff đã staged trước khi commit.

Đảm bảo **mvnw** giữ line ending phù hợp môi trường shell POSIX (thường **LF**) để tránh lỗi dạng **bad interpreter** do ký tự CRLF. Một quy tắc .gitattributes thường hữu ích là:

~~~gitattributes
mvnw text eol=lf
mvnw.cmd text eol=crlf
~~~

Điều này kiểm soát line ending, **không thay thế** việc lưu bit executable trong Git. Trong repository vốn có quy tắc line ending khác, hãy phối hợp với cấu hình chung trước khi bổ sung.

**Đừng bỏ sót thư mục .mvn/wrapper/** khi commit. Script hiện diện mà thiếu **maven-wrapper.properties** sẽ khiến việc xác định/tải phiên bản Maven không đúng kỳ vọng. Với type **bin** hoặc **source**, commit những thành phần bổ sung tương ứng mà Wrapper Plugin tạo ra.

## 7. Dùng cùng nguyên tắc trong CI

Nên để CI chạy **script từ repository** và chủ động cài JDK theo yêu cầu của POM. Ví dụ GitHub Actions kiểm tra trên Ubuntu và Windows:

~~~yaml
name: Maven Wrapper Build

on:
  push:
  pull_request:

jobs:
  verify:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Build on Linux
        if: runner.os == 'Linux'
        run: ./mvnw -B -ntp clean verify

      - name: Build on Windows
        if: runner.os == 'Windows'
        run: .\mvnw.cmd -B -ntp clean verify
~~~

Dự án thực tế cần đặt workflow dưới **.github/workflows/**. Ví dụ này minh họa cách gọi Wrapper; các phiên bản action trong workflow cần được nhóm quản lý theo chính sách CI của mình.

Ở job Linux, script **mvnw** phải có quyền thực thi sau checkout. Ở job Windows, PowerShell gọi trực tiếp **.\mvnw.cmd**. Cả hai dùng chung POM và properties từ cùng commit, cùng Java 17 được cài bởi bước setup.

Có thể điều chỉnh workflow cho macOS hoặc các JDK khác, nhưng nên chạy đúng tổ hợp môi trường sản phẩm thực sự hỗ trợ. Nếu dùng script trong Docker/CI shell khác, áp dụng cú pháp của shell đó; chẳng hạn trong container Linux thông thường vẫn là **./mvnw**.

## 8. Điều kiện để “nhất quán” có ý nghĩa

**Cùng phiên bản Maven là cần thiết nhưng chưa đủ.** Khi kết quả giữa hai máy khác nhau, kiểm tra lần lượt các yếu tố sau:

| Yếu tố | Cách giữ nhất quán |
| --- | --- |
| Phiên bản Maven | Commit và dùng chung **.mvn/wrapper/maven-wrapper.properties**, luôn chạy **mvnw/mvnw.cmd** của repository. |
| Phiên bản JDK | Khai báo **maven.compiler.release**, cài đúng JDK trên CI, so sánh dòng Java trong **Wrapper --version**. |
| Dependency và plugin | Khai báo/phân phối phiên bản ổn định trong POM/parent; tránh phụ thuộc vào **SNAPSHOT**, version range hoặc plugin version thiếu kiểm soát nếu cần build tái lập. |
| Profile và biến môi trường | Kiểm tra **-P**, **-D**, **JAVA_HOME**, **MAVEN_OPTS**, thông số hệ điều hành và secrets/cấu hình tác động đến build. |
| Repository và mirror | Quản lý **settings.xml**, proxy, certificate, mirror; tránh để các máy vô tình dùng nguồn artifact khác nhau. |
| Thư mục làm việc | Gọi Wrapper ở gốc dự án, giữ đường dẫn và lệnh nhất quán giữa local/CI. |
| File mode và line endings | Giữ executable bit cho **mvnw** và line ending phù hợp shell POSIX. |

Ví dụ, **./mvnw --version** có thể hiển thị đúng Maven 3.9.9 ở cả hai máy, nhưng một máy dùng JDK 17, máy kia dùng JDK 21. Nếu dự án cần Java 17, nên quản lý JDK rõ ràng; Wrapper không tự đổi phiên bản JDK.

Tương tự, nếu một người dùng **./mvnw -DskipTests package** còn CI chạy **./mvnw clean verify**, hai lần build không kiểm tra cùng điều kiện. Chuẩn hóa **goals, options và profile** cùng với phiên bản Maven. Không bỏ test chỉ để làm một môi trường “xanh”.

## 9. Xử lý lỗi thường gặp

**Lỗi 1 — Linux/macOS báo “Permission denied”.** Script không có bit executable. Dùng **chmod +x mvnw**, kiểm tra quyền trong Git index và commit quyền này để checkout ở CI cũng chạy được.

**Lỗi 2 — PowerShell báo không nhận diện được “mvnw.cmd”.** PowerShell không tự tìm file trong thư mục hiện tại theo tên trần. Chuyển đến gốc dự án rồi chạy **.\mvnw.cmd --version**. Nếu vẫn không thấy, kiểm tra rằng repository có **mvnw.cmd**.

**Lỗi 3 — “bad interpreter” hoặc ký tự ^M trong script mvnw.** Kiểm tra line ending **LF** của tệp POSIX; dùng .gitattributes nếu phù hợp. Không chạy **mvnw.cmd** như một shell script trên Linux.

**Lỗi 4 — “JAVA_HOME is not defined correctly” hoặc “java not found”.** Cài JDK phù hợp, đặt **JAVA_HOME** tới thư mục gốc của JDK theo hệ điều hành và đảm bảo Java truy cập được từ môi trường chạy. Kiểm tra **java -version** và **Wrapper --version**. Wrapper chọn phiên bản Maven, nhưng vẫn cần Java để chạy Maven.

**Lỗi 5 — Download Maven thất bại: DNS, proxy, TLS, HTTP hoặc offline.** Mở **.mvn/wrapper/maven-wrapper.properties** và kiểm tra **distributionUrl**; xác nhận mạng, proxy, chứng chỉ và quyền truy cập nguồn phân phối. Với kiểu **only-script**, quá trình tải dựa vào công cụ hệ điều hành như curl/wget (POSIX) hoặc PowerShell (Windows). Lần đầu cần truy cập được URL hoặc đã có bản phân phối trong bộ đệm. Tùy chọn Maven **-o** không thể tự giải quyết một bản phân phối Wrapper chưa được tải.

**Lỗi 6 — Một người dùng Maven khác phiên bản CI.** Kiểm tra cả hai có gọi **mvnw/mvnw.cmd** từ cùng commit và dùng cùng **distributionUrl** hay không. Một bên chạy **mvn** toàn cục có thể đang dùng phiên bản khác. So sánh **--version** trực tiếp từ Wrapper.

**Lỗi 7 — Build thành công trên Windows nhưng thất bại trên Linux.** Kiểm tra khác biệt chữ hoa/chữ thường của tên tệp, dấu phân cách đường dẫn, executable bit, charset, timezone, JDK, profile và lệnh đã chạy. Sửa cấu hình/script để portable thay vì cho rằng Wrapper sẽ tự chuẩn hóa mọi đặc điểm của hệ điều hành.

**Lỗi 8 — CI treo vì câu hỏi tương tác hoặc log tải quá dài.** Dùng **-B** để bật batch mode và **-ntp** nếu phiên bản Maven hỗ trợ. Xem mã thoát và log lỗi thực; đừng chỉ dựa vào dòng cuối.

**Lỗi 9 — Nghi ngờ tệp Maven tải về hoặc nguồn phân phối.** Kiểm tra URL đáng tin cậy. Apache Maven Wrapper hỗ trợ khóa **distributionSha256Sum** (và **wrapperSha256Sum** khi áp dụng cho wrapper JAR) trong properties để kiểm chứng SHA-256; chỉ khai báo checksum đã đối chiếu với đúng bản phân phối, tuyệt đối không tự đoán giá trị.

## 10. Quy trình đề xuất cho nhóm

1. **Chuẩn bị Wrapper một lần** cho repository và chọn phiên bản Maven phù hợp; commit **mvnw**, **mvnw.cmd**, **.mvn/wrapper/** cùng POM.
2. **Thống nhất lệnh build** trong README và CI: **./mvnw -B -ntp clean verify** trên POSIX; **.\mvnw.cmd -B -ntp clean verify** trên PowerShell; cú pháp cmd.exe tương ứng.
3. **Cố định JDK và các dependency/plugin quan trọng**; kiểm tra thực tế bằng **Wrapper --version** trên từng hệ điều hành được hỗ trợ.
4. **Kiểm thử qua ít nhất các môi trường cần hỗ trợ**; xem xét khả năng chạy từ checkout sạch với cache trống để phát hiện lỗi Wrapper, quyền thực thi hoặc mạng bootstrap.
5. **Nâng phiên bản Maven có kiểm soát**: sửa cấu hình Wrapper qua quy trình duy trì được chấp nhận, chạy CI đầy đủ, review thay đổi rồi commit chung với mã nguồn nếu cần.

Như vậy, **mvnw** và **mvnw.cmd** là hai cách khởi chạy theo hệ điều hành của **cùng cơ chế Maven Wrapper**. Sự nhất quán đến từ việc mọi môi trường lấy phiên bản Maven, POM, JDK yêu cầu và câu lệnh build từ cấu hình dự án được quản lý, thay vì lệ thuộc vào cài đặt Maven riêng của từng máy.

**Tài liệu tham khảo chính thức:**
- [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/)
- [Apache Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html)
