# Đưa dự án Maven đầu tiên lên Git cùng cấu hình và Maven Wrapper

## 1. Mục tiêu và bức tranh tổng thể

Một dự án Java chạy được trên máy người tạo chưa chắc chạy được trên máy người nhận: người đó có thể chưa cài Maven, đang dùng Maven khác phiên bản, thiếu JDK, thiếu tệp cấu hình hoặc chỉ nhận được mã nguồn mà không biết lệnh build. Đưa dự án Maven lên Git đúng cách có nghĩa là **lưu được toàn bộ đầu vào cần thiết để một người khác lấy mã về và build lại**, đồng thời tránh đưa tệp sinh ra, dữ liệu cá nhân hoặc bí mật vào lịch sử Git.

Sau bài này, bạn có thể:

1. Xác định những tệp Maven **cần được Git theo dõi** và những tệp **cần bỏ qua**.
2. Thêm **Apache Maven Wrapper** vào dự án, cố định một phiên bản Maven cụ thể và chạy build bằng `mvnw`/`mvnw.cmd`.
3. Tạo `.gitignore`, `.gitattributes` và `README.md` để dự án dùng được trên Windows, Linux, macOS.
4. Thực hiện `git init`, xem thay đổi, đưa đúng tệp vào staging, commit, kết nối remote và push.
5. Clone dự án sang môi trường mới, kiểm tra phiên bản Maven/JDK, build và chạy chương trình để chứng minh repository đủ đầu vào.
6. Nhận diện lỗi phổ biến: commit thiếu Wrapper, Git bỏ qua nhầm Wrapper, thiếu quyền thực thi, đẩy `target/` hoặc lộ tệp nhạy cảm.

**Mô hình cần nhớ:**

~~~text
Dự án trên máy A
  ├── pom.xml, src/, README.md, .gitignore
  ├── mvnw, mvnw.cmd, .mvn/wrapper/...
  └── Git commit ──> remote repository
                         │
                         ▼
                     Máy B / CI
                         │
                      git clone
                         │
                     ./mvnw verify
                         │
          Maven đúng phiên bản được tải/chạy
                         │
               biên dịch, kiểm thử, đóng gói
~~~

**Phân chia trách nhiệm:** Git lưu phiên bản của các tệp; `pom.xml` mô tả cách Maven build; Maven Wrapper cung cấp cách chọn/tải phiên bản Maven của dự án; **JDK vẫn phải được chuẩn bị riêng**, phù hợp yêu cầu của Maven, plugin và mã nguồn. Wrapper **không** tự đóng gói JDK vào Git.

## 2. Phân loại tệp trước khi commit

Giả sử dự án đơn mô-đun tên `hello-maven` có cấu trúc sau khi tạo Wrapper:

~~~text
hello-maven/
├── .gitignore
├── .gitattributes
├── README.md
├── pom.xml
├── mvnw
├── mvnw.cmd
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties
└── src/
    └── main/
        └── java/
            └── dev/
                └── example/
                    └── App.java
~~~

Ở chế độ Wrapper `only-script` được dùng trong bài, **không có yêu cầu phải có** `.mvn/wrapper/maven-wrapper.jar`. Một số chế độ Wrapper khác tạo thêm tệp như `maven-wrapper.jar` hoặc `MavenWrapperDownloader.java`; khi đã chọn chế độ đó, cần kiểm tra và theo dõi **đủ tệp bootstrap tương ứng**, thay vì xóa theo quy tắc “mọi tệp JAR đều là rác”.

| Thành phần | Có nên commit? | Lý do |
| --- | --- | --- |
| `pom.xml` | **Có** | Mô tả tọa độ dự án, plugin, dependency, Java release và cách build. |
| `src/main/`, `src/test/` | **Có** | Mã nguồn, tài nguyên và bài kiểm thử do nhóm duy trì. |
| `README.md` | **Có** | Hướng dẫn chạy và yêu cầu môi trường để người khác tự khởi động dự án. |
| `mvnw`, `mvnw.cmd` | **Có** | Script khởi động Maven Wrapper cho Unix và Windows. |
| `.mvn/wrapper/maven-wrapper.properties` | **Có** | Chứa `distributionUrl`, xác định bản Maven cần dùng. |
| Tệp Wrapper khác do chế độ đã chọn sinh ra | **Có, nếu cần để bootstrap** | Ví dụ `maven-wrapper.jar` ở chế độ `bin` hoặc mã downloader ở chế độ `source`. |
| `.mvn/maven.config`, `.mvn/jvm.config` | **Khi thực sự dùng** | Cấu hình chung của dự án; phải xem xét ảnh hưởng với mọi thành viên/CI. |
| `.gitignore`, `.gitattributes` | **Có** | Quy tắc bỏ qua tệp và chuẩn hóa phần liên quan đến Git. |
| `target/`, `*.class`, báo cáo sinh khi build | **Không** | Có thể tạo lại từ mã nguồn và cấu hình; dễ gây xung đột và làm repository phình to. |
| `.idea/`, `*.iml`, `.classpath`, `.settings/` | **Thường không** | Phần lớn là cấu hình riêng của máy/công cụ; chỉ chia sẻ tệp IDE được nhóm chủ động chuẩn hóa. |
| `.env`, token, private key, mật khẩu, `settings.xml` cá nhân | **Không** | Có nguy cơ lộ bí mật hoặc thông tin máy cá nhân. |

**Đừng nhầm `.mvn/` với `.m2/`:**

- `.mvn/` là thư mục **cấu hình ở gốc dự án**, chứa Wrapper và những cấu hình dùng chung; những tệp cần thiết phải được commit.
- `~/.m2/repository/` là **cache Maven cá nhân**; không đưa vào Git.
- `~/.m2/settings.xml` thường là cấu hình người dùng/mirror/credentials; không sao chép lên Git. Nếu công ty cần hướng dẫn cấu hình mirror, mô tả cách thiết lập trong README và phân phối bí mật qua cơ chế an toàn.

Git **không đưa nội dung thư mục `.git/` lên remote như tệp dự án**; `.git/` chứa lịch sử và cấu trúc quản lý local repository.

## 3. Chuẩn bị dự án Java tối thiểu, biên dịch được

Ví dụ sử dụng **JDK 17+**, **Maven 3.9.11** (một phiên bản cụ thể dùng cho bài tập, không hàm ý là bản mới nhất) và một lớp Java. Giả định Git và một bản Maven toàn cục đã được cài **một lần** để chạy plugin tạo Wrapper. Sau khi tạo xong Wrapper, người clone không cần cài Maven toàn cục.

Trong thư mục `hello-maven`, tạo `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>hello-maven</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tạo `src/main/java/dev/example/App.java`:

~~~java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from Maven + Git!");
    }
}
~~~

`App` là chương trình Java 17 chạy độc lập; ví dụ không cần thư viện thứ ba và không cần Spring Boot. Cấu hình `maven.compiler.release=17` tạo mã hướng tới Java 17 khi dùng compiler hỗ trợ `--release 17`; **nó không tự cài JDK 17**. Phiên bản `maven-compiler-plugin` được khai báo tường minh để dễ tái lập build.

Sau khi Maven Wrapper được tạo ở mục tiếp theo, lệnh kiểm chứng sẽ là:

~~~bash
./mvnw -B -ntp clean verify
java -cp target/classes dev.example.App
~~~

Nếu build thành công và chạy bằng JVM hỗ trợ Java 17, **stdout của lệnh `java` cuối** là:

~~~text
Hello from Maven + Git!
~~~

`clean verify` có thể tải plugin/dependency trong lần đầu, nên log Maven, thời lượng và số lượng tệp trong `target/` khác nhau theo môi trường. Với ví dụ này, lệnh Java đọc class trực tiếp từ `target/classes`, không dựa vào `Main-Class` manifest của JAR.

## 4. Tạo và cố định Maven Wrapper đúng cách

### 4.1. Maven Wrapper giải quyết việc gì?

Nếu chỉ đưa `pom.xml` lên Git, người clone có thể gọi `mvn` toàn cục với phiên bản Maven bất kỳ mà máy họ đang có. Điều này dễ tạo khác biệt do Maven core và các plugin thay đổi theo thời gian.

**Apache Maven Wrapper** cung cấp script `mvnw` (Unix) và `mvnw.cmd` (Windows) ở gốc repository. Script đọc `.mvn/wrapper/maven-wrapper.properties` để xác định bản phân phối Maven, tải về cache Wrapper khi chưa có rồi chạy Maven tương ứng.

Đây là hai lệnh khác nhau:

- `mvn verify`: dùng **Maven toàn cục** được shell tìm thấy.
- `./mvnw verify` hoặc `.\mvnw.cmd verify`: dùng **Maven do dự án khai báo trong Wrapper**.

Maven Wrapper **không thay thế JDK**. `JAVA_HOME`, Java trong `PATH`, yêu cầu Java tối thiểu của Maven và Java đích trong `pom.xml` vẫn cần kiểm tra.

### 4.2. Sinh Wrapper bằng plugin chính thức

Từ thư mục gốc chứa `pom.xml`, sử dụng bản Maven toàn cục để chạy plugin **một lần**:

~~~bash
mvn org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper -Dmaven=3.9.11 -Dtype=only-script
~~~

Ý nghĩa:

- `org.apache.maven.plugins:maven-wrapper-plugin:3.3.4:wrapper`: gọi rõ plugin, version và goal để tránh phụ thuộc vào cách Maven phân giải prefix plugin.
- `-Dmaven=3.9.11`: chọn **bản Maven mà thành viên nhóm sẽ dùng**; đây là phiên bản ví dụ đã phát hành.
- `-Dtype=only-script`: sử dụng script Wrapper, không cần đưa `maven-wrapper.jar` hay downloader Java vào repository.

Trên Unix, `only-script` dựa vào công cụ tải như `curl` hoặc `wget`; trên Windows, script dùng PowerShell để tải Maven. Máy chạy lần đầu cần quyền truy cập đến URL tải Maven, trừ khi bản phân phối đã nằm trong cache. Nếu mạng nội bộ chặn tải, phải chuẩn bị mirror phù hợp theo chính sách dự án; **không xóa Wrapper rồi quay về Maven toàn cục** như một cách sửa lâu dài.

Các chế độ Wrapper có thể gặp:

| `type` | Tệp bootstrap đặc trưng | Đánh đổi |
| --- | --- | --- |
| `only-script` | `mvnw`, `mvnw.cmd`, cấu hình `.mvn/wrapper/` | Gọn, không commit JAR; phụ thuộc công cụ tải và mạng ở lần đầu. |
| `script` | Script và các tài nguyên bootstrap mà plugin sinh ra | Cách bootstrap khác `only-script`; phải giữ đúng tệp cần thiết. |
| `bin` | Có `maven-wrapper.jar` | Có một JAR Wrapper cần được theo dõi trong Git. |
| `source` | Có `MavenWrapperDownloader.java` | Dùng mã Java bootstrap thay cho việc commit JAR Downloader. |

**Nguyên tắc:** chạy goal của Maven Wrapper Plugin, rồi **xem chính xác các tệp được sinh ra** bằng `git status`; danh sách trên là mô tả chế độ, không phải yêu cầu tự tạo thủ công mọi tệp.

### 4.3. Kiểm tra tệp cấu hình Wrapper

Tệp `.mvn/wrapper/maven-wrapper.properties` được plugin sinh ra phải chứa `distributionUrl` trỏ đến đúng phiên bản Maven. Ví dụ giá trị cho Maven 3.9.11:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.11/apache-maven-3.9.11-bin.zip
~~~

Ngoài `distributionUrl`, file do plugin tạo có thể có các thuộc tính khác liên quan đến cấu hình tải và xác thực checksum. **Giữ cấu hình thật do plugin tạo**, không xóa các khóa hợp lệ chỉ để file giống ví dụ rút gọn. Khi thay đổi `distributionUrl` để nâng Maven, hãy xem xét yêu cầu JDK, tính tương thích plugin và checksum trước khi commit.

Nếu cần tăng tính toàn vẹn nguồn tải, Maven Wrapper hỗ trợ `distributionSha256Sum` để xác minh SHA-256 bản phân phối; các chế độ sử dụng Wrapper JAR còn có `wrapperSha256Sum`. Hash phải lấy từ **nguồn phát hành đáng tin cậy** và khớp chính xác dữ liệu tải xuống. Không điền một chuỗi hash phỏng đoán.

### 4.4. Chạy Wrapper trên từng hệ điều hành

Linux/macOS (ở gốc dự án):

~~~bash
chmod +x mvnw
./mvnw -version
./mvnw -B -ntp clean verify
~~~

Windows PowerShell (ở gốc dự án):

~~~powershell
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
~~~

Windows Command Prompt:

~~~bat
mvnw.cmd -version
mvnw.cmd -B -ntp clean verify
~~~

`-B` giúp build chạy ở chế độ batch; `-ntp` giảm log tiến trình tải. Kết quả `-version` cần hiển thị **Apache Maven 3.9.11** cùng bản Java/JDK đang dùng. `mvnw` là tên script tại thư mục hiện tại, vì vậy trên Unix phải có `./` để shell chạy tệp đó.

Trên Windows, `mvnw.cmd` hoạt động mà không cần bit execute Unix. Trên Linux/macOS, quyền thực thi của `mvnw` là một phần quan trọng cần được Git lưu ở chế độ tệp `100755`.

## 5. Dùng `.gitignore` để loại tệp sinh ra và tệp riêng tư

Tạo `.gitignore` ở **gốc repository**, trước lần `git add` đầu tiên:

~~~gitignore
# Maven output (including modules if this becomes multi-module)
**/target/

# Common IDE workspace files
/.idea/
/.vscode/
*.iml
.classpath
.project
.settings/

# Local logs and editor temporary files
*.log
*~

# Local environment and secrets
.env
.env.*
!.env.example
~~~

Giải thích:

- `**/target/` bỏ qua thư mục output Maven ở gốc và trong các module con. **Không** bỏ qua `src/` hay `pom.xml`.
- Các quy tắc IDE giúp giảm xung đột giữa máy người dùng; nếu nhóm quyết định chia sẻ một cấu hình IDE cụ thể, hãy chỉnh quy tắc một cách có chủ đích.
- `.env` và `.env.*` giữ bí mật local ngoài Git; `!.env.example` cho phép commit một **mẫu không chứa bí mật** khi dự án thực sự cần mẫu đó.
- `.gitignore` chỉ áp dụng cho tệp **chưa được Git theo dõi**. Nếu `target/` hoặc `.env` đã được commit trước đó, thêm quy tắc ignore không tự xóa chúng khỏi lịch sử.

**Không viết một quy tắc chung như `.mvn/` hoặc `*.jar` nếu chưa đánh giá tác động.** Quy tắc `.mvn/` có thể che luôn tệp Wrapper bắt buộc. Quy tắc `*.jar` có thể vô tình che `.mvn/wrapper/maven-wrapper.jar` ở chế độ `bin`.

Kiểm tra quy tắc và lý do tệp bị bỏ qua:

~~~bash
git check-ignore -v target/classes/dev/example/App.class
git check-ignore -v .mvn/wrapper/maven-wrapper.properties
git status --short --untracked-files=all
~~~

Nếu `git check-ignore` in ra một quy tắc cho `target/classes/...` thì hành vi bỏ qua output là đúng. Đối với `maven-wrapper.properties`, **bình thường không có quy tắc ignore nào khớp**; `git check-ignore` có thể thoát với mã `1` khi không tìm thấy quy tắc, đây không phải lỗi cấu hình.

Nếu một tệp không được Git nhận diện vì đã commit trước đó hoặc được ignore bởi quy tắc toàn cục, so sánh `git ls-files`, `git status` và `git check-ignore -v` để phân biệt **đã tracked** với **đang ignored**.

## 6. Giữ kết thúc dòng và quyền thực thi ổn định

Unix shell script `mvnw` cần dòng kết thúc LF. Khi repository có người dùng Windows và Unix, hãy tạo thêm `.gitattributes` ở gốc:

~~~gitattributes
* text=auto
/mvnw text eol=lf
/mvnw.cmd text eol=crlf
~~~

`text=auto` cho phép Git xử lý văn bản thông thường; hai quy tắc cụ thể giữ LF cho script Unix và CRLF cho script Windows. Tệp nhị phân được Git nhận diện là nhị phân và không đổi xuống dòng. Nếu repository đã tồn tại, việc thêm quy tắc này có thể làm Git xem xét lại kết thúc dòng ở một số file; kiểm tra diff trước khi commit thay đổi hàng loạt.

Sau khi `git add mvnw`, kiểm tra Git ghi quyền file:

~~~bash
git ls-files --stage mvnw
~~~

Ở cột mode, mong đợi `100755`. Nếu đang dùng Git trên Windows và quyền thực thi chưa được ghi đúng, có thể đặt trực tiếp trong Git index:

~~~bash
git update-index --chmod=+x mvnw
git ls-files --stage mvnw
~~~

Đặt bit execute ở Git index vẫn cần file trên Unix có quyền chạy phù hợp sau checkout. Đối với dự án mới, `.gitattributes` và quyền thực thi nên có **ngay trong commit đầu tiên** để người clone trên Linux không phải tự sửa bằng `chmod`.

## 7. Viết README đủ để người khác tự build

Tệp `README.md` nên trả lời năm câu hỏi: dự án làm gì, cần JDK nào, dùng lệnh nào, chạy chương trình ra sao và kiểm thử ở đâu. Ví dụ nội dung phù hợp với dự án `hello-maven`:

~~~markdown
# Hello Maven

Dự án Java 17 tối thiểu dùng Maven Wrapper để biên dịch và kiểm chứng build.

## Yêu cầu
- Git.
- JDK 17 trở lên, có lệnh `java` và `javac`.
- Internet ở lần chạy Wrapper đầu (hoặc cache/mirror Maven đã chuẩn bị).

## Kiểm tra và build
Linux/macOS:

    ./mvnw -version
    ./mvnw -B -ntp clean verify

Windows PowerShell:

    .\mvnw.cmd -version
    .\mvnw.cmd -B -ntp clean verify

## Chạy chương trình

    java -cp target/classes dev.example.App

Kết quả mong đợi:

    Hello from Maven + Git!

Phiên bản Maven dùng theo .mvn/wrapper/maven-wrapper.properties.
Không cần cài Maven toàn cục sau khi Wrapper đã được tạo.
~~~

README không nên ghi mật khẩu, token, đường dẫn absolute phụ thuộc máy hay hướng dẫn chép `settings.xml` cá nhân lên repository. Khi dự án lớn hơn, bổ sung cách chạy test, cấu hình biến môi trường công khai, yêu cầu database/infra và quy trình đóng góp.

## 8. Khởi tạo Git và tạo commit đầu tiên

Từ thư mục `hello-maven` **đã có** `pom.xml`, `src/`, Wrapper, `README.md`, `.gitignore` và `.gitattributes`:

~~~bash
git --version
git init -b main
git status --short --untracked-files=all
~~~

`git init -b main` tạo repository và chọn nhánh ban đầu `main` (được hỗ trợ ở các bản Git hiện đại). `git init` **không** tự đẩy dự án lên GitHub/GitLab và cũng không tự tạo remote.

Nếu đây là lần đầu sử dụng Git trên máy, cần cấu hình tên và email tác giả commit theo danh tính công việc của bạn bằng `git config user.name` và `git config user.email`, sau đó kiểm tra bằng `git config --get user.name` và `git config --get user.email`. Không dùng tài khoản người khác hoặc thông tin giả chỉ để vượt qua thông báo Git.

### 8.1. Xem thay đổi trước khi đưa vào staging

~~~bash
git status --short --untracked-files=all
~~~

Ký hiệu thường gặp:

- `??`: tệp chưa được Git theo dõi.
- `A` ở cột staging: tệp mới đã được đưa vào staging.
- `M`: tệp có thay đổi; vị trí ký hiệu phụ thuộc trạng thái staging và working tree.
- Không thấy `target/`: bình thường nếu tệp đã được `.gitignore` bỏ qua.

Đưa **đúng các đầu vào cần thiết** vào staging:

~~~bash
git add .gitignore .gitattributes README.md pom.xml src mvnw mvnw.cmd .mvn/wrapper
git update-index --chmod=+x mvnw
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
~~~

Với `type=only-script`, `git add .mvn/wrapper` sẽ đưa `maven-wrapper.properties` và các tệp Wrapper thực sự được plugin tạo vào staging. `git diff --cached --check` giúp phát hiện một số vấn đề khoảng trắng; `--name-only` và `--stat` giúp rà soát toàn bộ tệp sắp commit.

**Đọc lại danh sách đã staged:** phải thấy `pom.xml`, class Java, hai script Wrapper, `.mvn/wrapper/maven-wrapper.properties`, `.gitignore` và `README.md`; không được thấy `target/` hay bí mật. Cần xem nội dung cụ thể có thể dùng `git diff --cached` trước khi ghi lịch sử.

Đặt tên commit mô tả rõ kết quả:

~~~bash
git commit -m "chore: initialize Maven project with wrapper"
git log -1 --oneline
git status --short
~~~

`git status --short` thường không in gì ngay sau commit nếu working tree sạch và `target/` đã bị bỏ qua. Lịch sử commit chỉ chứa snapshot **đã staged**, không tự gồm tệp bạn quên `git add`.

### 8.2. Giữ những thay đổi bí mật ngoài lịch sử

Trước khi commit, rà `git diff --cached` và đường dẫn trong `git diff --cached --name-only`. Nếu vô tình stage tệp nhạy cảm **nhưng chưa commit**, sử dụng `git restore --staged` với đúng đường dẫn để đưa khỏi staging, rồi cập nhật `.gitignore`. Nếu đã commit hoặc push bí mật, cần **thu hồi/thay thế credential ngay** và xử lý lịch sử theo quy trình bảo mật; xóa file ở commit tiếp theo không bảo đảm bí mật không còn trong lịch sử cũ.

Không dùng `git add -f` để ép thêm tệp đã ignore trừ khi hiểu chính xác lý do. Với các tệp có chứa secret, đừng kiểm tra nguồn bằng cách in thẳng giá trị bí mật ra log CI.

## 9. Kết nối repository từ xa và push

**Git local repository** và **remote repository** là hai thứ khác nhau. Sau `git init` và commit, mã nguồn chỉ nằm trên máy của bạn cho đến khi có remote và `git push` thành công.

Quy trình thường dùng:

1. Tạo **repository trống** trên dịch vụ nhóm sử dụng (GitHub, GitLab hoặc Git server nội bộ). Nếu đã có commit khởi tạo trên remote (ví dụ README tự sinh), kiểm tra và hợp nhất lịch sử có chủ đích trước khi push.
2. Copy **địa chỉ Git remote thật** từ giao diện dịch vụ. Thiết lập bằng `git remote add origin` kèm địa chỉ đó, sử dụng HTTPS hoặc SSH theo cấu hình đã được cấp.
3. Kiểm tra `git remote -v`, `git branch --show-current`; xác nhận remote đúng repository và nhánh hiện tại là `main`.
4. Chạy `git push -u origin main` để đẩy commit đầu tiên và thiết lập nhánh upstream khi remote cho phép.
5. Kiểm tra trên giao diện remote rằng các tệp `pom.xml`, `src/`, `mvnw`, `mvnw.cmd`, `.mvn/wrapper/` xuất hiện trong commit mới. Nếu push bị từ chối do quyền hoặc chính sách nhánh, dùng quy trình quyền truy cập/PR của nhóm.

`git push` cần cơ chế xác thực do dịch vụ hỗ trợ; không ghi password hoặc access token trực tiếp trong đường dẫn remote, command history hay `README.md`. Nếu đã có một remote tên `origin`, hãy xem `git remote -v` và điều chỉnh theo quyết định của nhóm thay vì tùy tiện ghi đè.

Không dùng `git push --force` để xử lý lỗi push đầu tiên. Lệnh đó có thể thay lịch sử nhánh remote ngoài dự kiến.

## 10. Kiểm thử quan trọng nhất: clone ở nơi khác rồi build bằng Wrapper

**Commit thành công chưa chứng minh dự án có thể tái tạo.** Điều cần kiểm chứng là một bản clone sạch với JDK phù hợp có thể chạy Wrapper và build dù máy không có Maven toàn cục.

Từ một thư mục khác dự án gốc, clone bằng URL remote của repository vừa tạo. Khi đã vào bản clone, chạy:

Linux/macOS:

~~~bash
git status --short
./mvnw -version
./mvnw -B -ntp clean verify
java -cp target/classes dev.example.App
~~~

Windows PowerShell:

~~~powershell
git status --short
.\mvnw.cmd -version
.\mvnw.cmd -B -ntp clean verify
java -cp target/classes dev.example.App
~~~

**Bộ bằng chứng PASS:**

| Kiểm tra | Dấu hiệu đạt |
| --- | --- |
| `git status --short` ngay sau clone | Không có thay đổi bất ngờ trong working tree. |
| Wrapper `-version` | Hiển thị Maven **3.9.11** và Java phù hợp (ví dụ JDK 17 hoặc 21). |
| `clean verify` | Build kết thúc thành công, không thiếu `pom.xml`, source hoặc plugin. |
| Chạy `dev.example.App` | In đúng `Hello from Maven + Git!`. |
| `git status --short` sau build | `target/` không xuất hiện như tệp mới cần commit. |
| `git ls-files .mvn/wrapper` | Có tệp `maven-wrapper.properties` và các tài nguyên Wrapper cần thiết của chế độ đã chọn. |

Nếu build chỉ thành công ở máy gốc, kiểm tra xem có phụ thuộc không được khai báo, tệp cấu hình chưa commit, `settings.xml` cá nhân, cache Maven hoặc plugin dùng sai phiên bản không. Với bài ví dụ chỉ dùng Java SE, phạm vi phân tích nhỏ nên dễ tìm lỗi hơn.

**Nhớ rằng:** JDK vẫn phải được cài trên máy clone; Wrapper có thể cần tải Maven và plugin ở lần đầu. Build offline thành công chỉ khi mọi bản phân phối/artifact cần thiết đã có sẵn trong cache/mirror.

## 11. Vẫn có thể xảy ra khác biệt môi trường dù đã có Wrapper

Wrapper giúp cố định **Maven core**. Để nhóm tái tạo build đáng tin cậy hơn, kiểm soát thêm:

1. **JDK:** ghi rõ bản Java và `JAVA_HOME` cho máy thành viên/CI; có thể dùng cơ chế quản lý JDK của nhóm. `mvnw` không quyết định JDK thay IDE/CI.
2. **Plugin và dependency:** khai báo phiên bản plugin cần thiết trong `pom.xml` (hoặc `pluginManagement` của parent); tránh version range hoặc snapshot thay đổi ngoài kiểm soát khi mục tiêu là build ổn định.
3. **Cấu hình local:** các tệp thực sự dùng chung trong `.mvn/` được commit; bí mật, token, đường dẫn máy cá nhân nằm trong biến môi trường, secret store hoặc user `settings.xml` ở ngoài Git.
4. **Repository/mirror:** nếu công ty dùng Nexus/Artifactory, tài liệu hóa cách người dùng cấu hình mirror. Không hardcode thông tin đăng nhập trong `distributionUrl` hay `pom.xml`.
5. **Tính toàn vẹn tải xuống:** xem xét cấu hình checksum SHA-256 của Maven Wrapper, duyệt URL phân phối, cập nhật Wrapper và plugin từ nguồn chính thức.
6. **Hệ điều hành:** giữ script Unix/Windows và kết thúc dòng phù hợp; thử clone/build trên môi trường mục tiêu thật.
7. **CI:** pipeline nên checkout mã, cài JDK rồi chạy **`./mvnw`**, không âm thầm dùng `mvn` toàn cục; đồng thời bảo đảm quyền thực thi và quyền truy cập kho artifact.
8. **Test:** `verify` chỉ chạy được những kiểm thử đã được dự án khai báo và plugin cấu hình. Build xanh không tự chứng minh mọi hành vi nghiệp vụ đều đúng.

Ví dụ, `pom.xml` có dependency mới chỉ cần Maven 3.9.11 nhưng plugin chạy test yêu cầu JDK 21; máy clone có JDK 17 vẫn thất bại dù Wrapper chọn đúng Maven. Cần xem đồng thời **Maven/JDK/plugin/JDK đích**.

## 12. Lỗi thường gặp khi đưa dự án Maven lên Git

### Lỗi 1: Bản clone báo thiếu `mvnw` hoặc `mvnw.cmd`

**Nguyên nhân:** chưa sinh Wrapper, chưa `git add` hoặc đã ignore nhầm script.

**Cách xử lý:** kiểm tra `git ls-files mvnw mvnw.cmd .mvn/wrapper` ở repository gốc; sinh Wrapper bằng plugin chính thức nếu thiếu; stage, commit và push đầy đủ. Không chép script Wrapper tùy tiện từ dự án không rõ nguồn gốc.

### Lỗi 2: `./mvnw: Permission denied` trên Linux/macOS

**Nguyên nhân:** `mvnw` không có bit executable.

**Cách xử lý:** trên máy phát triển dùng `chmod +x mvnw`, kiểm tra mode Git bằng `git ls-files --stage mvnw`, nếu cần `git update-index --chmod=+x mvnw` rồi commit. Trong tình huống tạm thời có thể chạy `sh ./mvnw -version` khi script hợp lệ; tuy nhiên repository nên lưu quyền chạy chuẩn.

### Lỗi 3: `/bin/sh` báo lỗi ký tự `\r` hoặc `bad interpreter`

**Nguyên nhân:** tệp `mvnw` của Unix bị chuyển sang dòng kết thúc CRLF.

**Cách xử lý:** dùng `.gitattributes` để giữ `/mvnw text eol=lf`, xác nhận file checkout có LF rồi commit sửa đúng tệp. Không sửa mã Java để khắc phục lỗi của shell script.

### Lỗi 4: Wrapper tải Maven thất bại

**Nguyên nhân:** sai `distributionUrl`, mạng/SSL/proxy chặn tải, máy thiếu công cụ tải cho chế độ Wrapper đang dùng hoặc repository mirror cần cấu hình.

**Cách xử lý:** đọc `.mvn/wrapper/maven-wrapper.properties`; kiểm tra URL, DNS/TLS, proxy và chính sách mạng; cấu hình mirror theo hướng dẫn chính thức. Không đổi sang một URL ngẫu nhiên và không bỏ qua xác thực checksum.

### Lỗi 5: Maven khởi động được nhưng báo `invalid target release`

**Nguyên nhân:** JDK biên dịch cũ hơn `maven.compiler.release`, hoặc JDK Maven/IDE khác bản người dùng tưởng.

**Cách xử lý:** chạy `java -version`, `javac -version`, `./mvnw -version`; xác nhận compiler thực tế và Java đích. Với `release=17`, cần compiler hỗ trợ Java 17.

### Lỗi 6: `target/` hoặc `.env` vẫn xuất hiện trên remote dù có `.gitignore`

**Nguyên nhân:** Git đã theo dõi các tệp này **trước khi** áp dụng ignore.

**Cách xử lý:** xác nhận bằng `git ls-files`; bỏ tracking bằng `git rm --cached` với đúng tệp/đường dẫn, kiểm tra staging rồi commit. Nếu nội dung nhạy cảm từng được push, phải xử lý cả vòng đời bí mật và lịch sử Git, không chỉ xóa tệp ở hiện tại.

### Lỗi 7: `pom.xml` có nhưng project clone không build được

**Nguyên nhân thường gặp:** `src/` hoặc tài nguyên dùng bởi build chưa commit; plugin dùng tệp nằm ngoài repo; Java khác phiên bản; dependency tải từ repository không còn truy cập được.

**Cách xử lý:** kiểm tra các đường dẫn do `pom.xml` tham chiếu, `git ls-files`, `./mvnw -version`, log build và cách cài JDK. Không nên commit cả `target/` để “sửa” việc thiếu đầu vào; hãy bổ sung đúng mã nguồn/cấu hình đã bị bỏ sót.

### Lỗi 8: Push bị từ chối hoặc remote không đúng

**Nguyên nhân:** remote sai, chưa có quyền, token/SSH chưa thiết lập hoặc nhánh remote đã có lịch sử khác.

**Cách xử lý:** xem `git remote -v`, `git branch -vv` và thông báo server; xác nhận quyền và quy trình nhánh. Không dùng force push như bước khắc phục mặc định.

## 13. Thực hành tự đánh giá

**Bài tập A — tạo commit tối thiểu:** tạo `hello-maven` đúng như mục 3, sinh Wrapper `only-script` cho Maven 3.9.11, thêm `README.md`, `.gitignore` và `.gitattributes`, sau đó commit. Trả lời: Git đã theo dõi những tệp nào? Tệp nào được bỏ qua? Mode của `mvnw` trong Git là gì?

**Bài tập B — thử nghiệm `.gitignore`:** chạy build, quan sát `target/` xuất hiện trên ổ đĩa nhưng không nằm trong `git status`. Dùng `git check-ignore -v` để tìm quy tắc đã bỏ qua `target/classes/dev/example/App.class`. Giải thích vì sao `pom.xml` không bị bỏ qua.

**Bài tập C — kiểm tra Wrapper:** so sánh kết quả `mvn -version` toàn cục (nếu cài) với `./mvnw -version` (hoặc `.\mvnw.cmd -version`). Kết luận: nhóm đã cố định phiên bản **Maven** hay cả **JDK**? Chỉ ra tệp lưu phiên bản Maven.

**Bài tập D — clone/build:** push lên remote do bạn quản lý, clone sang thư mục khác (hoặc máy CI có JDK 17), chạy Wrapper `clean verify` và chương trình. Xác nhận in đúng `Hello from Maven + Git!` và không phát sinh file tracked ngoài dự kiến.

**Câu hỏi kiểm tra:** Nếu bạn chỉ commit `pom.xml` và `src/` rồi bảo người khác chạy `mvn verify`, đã đủ tái lập bản Maven của nhóm chưa? **Chưa**: Maven toàn cục ở mỗi máy có thể khác nhau; cần commit Wrapper và hướng dẫn dùng Wrapper. Nếu bạn commit `mvnw` nhưng quên `.mvn/wrapper/maven-wrapper.properties` thì sao? **Không có cấu hình phân phối Maven cần thiết**; bản clone không thể dùng Wrapper theo đúng dự án.

## 14. Checklist trước khi bàn giao repository

- [ ] `pom.xml` mô tả dự án, khai báo Java release và phiên bản plugin quan trọng.
- [ ] Mã nguồn, tài nguyên và kiểm thử cần thiết đã được Git theo dõi.
- [ ] `mvnw`, `mvnw.cmd` và **toàn bộ tài nguyên Wrapper cần thiết** ở `.mvn/wrapper/` đã được commit.
- [ ] `distributionUrl` trỏ đúng bản Maven đã chọn, được kiểm tra bằng Wrapper `-version`.
- [ ] `mvnw` có quyền thực thi trên Unix; `.gitattributes` bảo toàn dòng kết thúc phù hợp.
- [ ] `.gitignore` loại `target/` và tệp riêng tư, không ẩn nhầm Wrapper.
- [ ] Không có bí mật, cache Maven, output build hoặc cấu hình máy cá nhân trong commit.
- [ ] `README.md` ghi rõ JDK, cách build bằng Wrapper, cách chạy ứng dụng.
- [ ] Đã rà soát `git diff --cached` trước commit và kiểm tra nội dung trên remote sau push.
- [ ] Đã **clone sạch và build bằng Wrapper**, chạy chương trình thành công.
- [ ] Nếu có CI, CI cũng sử dụng JDK phù hợp và Maven Wrapper của repository.

## 15. Tài liệu tham khảo chính thức

1. [Apache Maven Wrapper](https://maven.apache.org/tools/wrapper/) — cơ chế Wrapper, dạng phân phối và xác minh checksum.
2. [Maven Wrapper Plugin — Usage](https://maven.apache.org/tools/wrapper/maven-wrapper-plugin/usage.html) — lệnh `wrapper:wrapper`, `-Dmaven` và `-Dtype=only-script`.
3. [Apache Maven — POM Reference](https://maven.apache.org/pom.html) — ý nghĩa `pom.xml`.
4. [Git Book — Recording Changes to the Repository](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository) — staged/tracked, `git add` và commit.
5. [Git — gitignore](https://git-scm.com/docs/gitignore) — quy tắc ignore và giới hạn đối với tệp đã tracked.
6. [Git — git-check-ignore](https://git-scm.com/docs/git-check-ignore) — kiểm tra vì sao Git bỏ qua một đường dẫn.
