# Nâng cấp Gradle Wrapper và xử lý quyền thực thi, đường dẫn, proxy

## 1. Mục tiêu và phạm vi

**Gradle Wrapper** cho phép một dự án dùng phiên bản Gradle do chính dự án chỉ định, kể cả trên máy chưa cài lệnh **gradle** toàn cục. Khi làm việc nhóm hoặc chạy CI, Wrapper là cách khởi động build nên được ưu tiên. Bài học tập trung vào ba nhóm công việc có quan hệ chặt chẽ:

1. **Nâng cấp Wrapper an toàn:** chọn bản Gradle tương thích, cập nhật đầy đủ các file Wrapper, xác minh bản phân phối và kiểm thử lại build.
2. **Xử lý lỗi môi trường và đường dẫn:** quyền thực thi trên Unix, file mode trong Git, line ending, thư mục gọi lệnh, Java/JDK và các đường dẫn cache.
3. **Xử lý mạng/proxy:** phân biệt tải Gradle distribution với tải dependency, cấu hình HTTP/HTTPS proxy đúng chỗ, xử lý xác thực, timeout và chứng chỉ TLS.

Sau khi học, bạn có thể tự trả lời: “Tại sao cùng một repo chạy được trên Windows nhưng CI Linux báo Permission denied?”, “Vì sao Wrapper đã đổi version mà JAR/script vẫn cũ?”, và “Vì sao curl tải được file nhưng Gradle vẫn không vào được mạng?”.

## 2. Wrapper hoạt động như thế nào?

### 2.1. Bốn file cần nhận diện

Một dự án đã có Wrapper thường có cấu trúc:

~~~text
gradle-project/
├── settings.gradle             # Hoặc settings.gradle.kts
├── build.gradle                # Hoặc build.gradle.kts
├── gradlew                     # Script cho Linux/macOS
├── gradlew.bat                 # Script cho Windows
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

| File | Vai trò | Có đưa vào Git? |
| --- | --- | --- |
| **gradlew** | Shell script khởi động Wrapper trên Linux/macOS. | Có, giữ executable bit. |
| **gradlew.bat** | Batch script khởi động Wrapper trên Windows. | Có. |
| **gradle/wrapper/gradle-wrapper.jar** | Mã Java bootstrap để tìm, tải và khởi chạy Gradle distribution. | Có, xác minh nguồn gốc/checksum. |
| **gradle/wrapper/gradle-wrapper.properties** | Cấu hình distribution URL, checksum, đường dẫn lưu và tùy chọn tải. | Có, không nhúng secret. |

Không nên thêm **.gradle/** hoặc **build/** vào commit: đó là cache và đầu ra phát sinh. Ngược lại, **gradle/wrapper/gradle-wrapper.jar** phải được lưu trong repo dù là file nhị phân nhỏ, vì máy chưa có Gradle cần chính JAR này để bootstrap.

Luồng khởi động:

~~~text
./gradlew hoặc .\gradlew.bat
             |
             v
Kiểm tra Java để chạy gradle-wrapper.jar
             |
             v
Đọc gradle/wrapper/gradle-wrapper.properties
             |
             v
Có Gradle distribution phù hợp trong cache?
        /                          \
      Có                          Chưa
       |                            |
       |                 Tải ZIP qua mạng/proxy
       |                            |
       |                 Kiểm tra SHA-256 nếu có cấu hình
       |                            |
       |                 Giải nén vào Wrapper cache
        \                          /
         v                        v
                 Chạy Gradle
                     |
                     v
          Cấu hình project, chạy task
~~~

**Hai lần tải khác nhau cần phân biệt:** (1) Wrapper tải **bản phân phối Gradle** được trỏ tới bởi **distributionUrl**; (2) bản Gradle đã khởi động mới giải quyết **plugin và library dependencies** từ các repository như Maven Central. Một lỗi mạng ở bước (1) xảy ra trước khi logic build của dự án chạy; sửa **repositories { ... }** trong **build.gradle** không giải quyết lỗi tải distribution.

### 2.2. Bốn giá trị dễ nhầm

- **Gradle version:** phiên bản thực thi được ghim trong Wrapper, xem qua **./gradlew --version** hoặc **distributionUrl**.
- **Wrapper JAR/script version:** phiên bản mã bootstrap đã sinh ra các file Wrapper; sau lần chạy upgrade đầu tiên có thể vẫn là bản cũ.
- **JDK chạy Gradle:** runtime Java dùng để khởi động Gradle; chịu ảnh hưởng bởi môi trường Java, yêu cầu phiên bản của Gradle và cấu hình daemon.
- **Java toolchain:** JDK dùng biên dịch/kiểm thử chương trình, có thể khác JDK chạy Gradle.

Nâng Gradle lên bản mới chưa có nghĩa tự động đổi JDK của source code hoặc nâng tất cả plugin, dependency. Ngược lại, JDK quá cũ có thể làm Wrapper tải xong nhưng Gradle mới không khởi động được.

## 3. Quy trình nâng cấp Wrapper có kiểm soát

### 3.1. Trước khi nâng cấp

1. Xác định **bản Gradle hiện tại** bằng **./gradlew --version** (Linux/macOS) hoặc **.\gradlew.bat --version** (Windows PowerShell).
2. Đọc file **gradle/wrapper/gradle-wrapper.properties** để biết bản đích hiện tại, **-bin** hay **-all**, checksum, URL nội bộ, timeout hoặc cài đặt mirror.
3. Kiểm tra **release notes**, yêu cầu JDK chạy Gradle và khả năng tương thích của plugin quan trọng (ví dụ Spring Boot, Android Gradle Plugin, Kotlin, plugin nội bộ). Đừng nâng phiên bản chỉ vì nó mới nhất.
4. Đảm bảo repository ở trạng thái đã lưu các thay đổi công việc quan trọng vào Git; thực hiện upgrade trên một nhánh riêng khi cần review.
5. Chạy kiểm thử baseline, ví dụ **./gradlew help** và **./gradlew build**, để biết điều gì đã hỏng từ trước thay vì quy lỗi cho upgrade.

Có thể kiểm tra nhanh tại root project:

**Linux/macOS (Bash):**

~~~bash
pwd
ls -l gradlew gradlew.bat gradle/wrapper/
cat gradle/wrapper/gradle-wrapper.properties
java -version
./gradlew --version
./gradlew help
~~~

**Windows PowerShell:**

~~~powershell
Get-Location
Get-ChildItem .\gradlew*, .\gradle\wrapper\
Get-Content .\gradle\wrapper\gradle-wrapper.properties
java -version
.\gradlew.bat --version
.\gradlew.bat help
~~~

Nếu các lệnh này chưa chạy được, giải quyết lỗi Java, quyền, đường dẫn hoặc mạng ở các mục sau trước khi kết luận phiên bản Gradle mới không tương thích.

### 3.2. Chọn version cụ thể và lấy checksum

Ví dụ dưới đây dùng **Gradle 9.9.0**, một bản được phân phối chính thức. Đây là **phiên bản minh họa**, chỉ nâng đến nó khi plugin và JDK của dự án tương thích. Lưu số phiên bản chính xác như **9.9.0** thay vì tự động chọn **latest** để CI và các máy có cùng đầu vào.

Gradle cung cấp hai loại distribution:

- **bin:** runtime cần cho build; kích thước nhỏ hơn, thường phù hợp cho developer/CI.
- **all:** thêm source/documentation của Gradle; hữu ích trong một số tình huống IDE/debug nhưng tải nặng hơn.

Kiểm tra checksum SHA-256 chính thức trên **https://gradle.org/release-checksums/**; file checksum tương ứng với bản **bin** của ví dụ có địa chỉ:

~~~text
https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256
~~~

Mỗi checksum phải khớp **đúng version và đúng loại distribution**. Không lấy checksum của **-all.zip** cho **-bin.zip**.

**Linux/macOS (Bash; cần curl):**

~~~bash
checksum=$(curl -fsSL https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256)
printf '%s\n' "$checksum"
~~~

**Windows PowerShell:**

~~~powershell
$checksum = (Invoke-RestMethod -Uri 'https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256').Trim()
$checksum
~~~

Giá trị trả về phải là chuỗi SHA-256 gồm 64 ký tự hệ thập lục phân. Đối chiếu với trang checksum chính thức trước khi dùng. Cần truy cập HTTPS được tin cậy; nếu môi trường không tải được checksum, tìm nguyên nhân mạng thay vì tự điền một chuỗi đoán.

### 3.3. Chạy task wrapper hai lần

Từ **root project**, sử dụng Wrapper **đã có** để thực thi task **:wrapper**. Dấu hai chấm hướng tới task ở root, đặc biệt hữu ích trong multi-project build.

**Linux/macOS (Bash, tiếp tục dùng biến checksum vừa lấy):**

~~~bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin --gradle-distribution-sha256-sum "$checksum"
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin --gradle-distribution-sha256-sum "$checksum"
./gradlew --version
~~~

**Windows PowerShell (tiếp tục dùng biến checksum vừa lấy):**

~~~powershell
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin --gradle-distribution-sha256-sum $checksum
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin --gradle-distribution-sha256-sum $checksum
.\gradlew.bat --version
~~~

**Vì sao chạy hai lần?**

- **Lần 1:** phiên bản Gradle cũ chạy task **:wrapper**, cập nhật cấu hình trỏ đến bản mới (đặc biệt **gradle-wrapper.properties**). Wrapper JAR/script có thể vẫn được tạo bằng bản Gradle cũ.
- **Lần 2:** script khởi động tải/chạy bản Gradle mới theo cấu hình vừa đổi, rồi sinh lại Wrapper JAR và script bằng mã của phiên bản mới.
- **Sau cùng:** lệnh **--version** phải hiển thị **Gradle 9.9.0** trong ví dụ, và build/test phải chạy lại thành công.

Nếu chạy lần 1 thành công nhưng lần 2 báo lỗi khi tải Gradle mới hoặc plugin không tương thích, phải xử lý lỗi đó trước. Không đánh dấu upgrade hoàn tất chỉ vì **distributionUrl** đã thay đổi.

Trên dự án cũ không hỗ trợ tùy chọn **--gradle-distribution-sha256-sum** hoặc đang có cấu hình đặc biệt, tra tài liệu của phiên bản hiện tại để chọn lộ trình trung gian. Thay đổi thủ công **distributionUrl** chỉ nên là biện pháp khôi phục có kiểm chứng; việc đó không tự cập nhật JAR/script.

### 3.4. Trường hợp dự án chưa có Wrapper

Chỉ để **khởi tạo** Wrapper, cần có Gradle CLI đã cài từ nguồn đáng tin trên một máy:

~~~bash
gradle :wrapper --gradle-version 9.9.0 --distribution-type bin
~~~

Sau đó thiết lập **distributionSha256Sum** đúng giá trị chính thức và chạy lại task **:wrapper** bằng Wrapper để đồng bộ các file. Với dự án đã có Wrapper, thường **không cần** cài Gradle toàn cục hoặc dùng lệnh **gradle build**.

### 3.5. Kiểm tra file thay đổi và commit

Sau upgrade:

~~~bash
git status --short
git diff --check
git diff -- gradle/wrapper/gradle-wrapper.properties gradlew gradlew.bat
git ls-files -s gradlew
~~~

Cần review đủ bốn file Wrapper. **gradle-wrapper.jar** là nhị phân nên **git diff** thường chỉ cho biết file thay đổi; phải kiểm tra checksum nguồn gốc riêng. Script **gradlew** nên có Git mode **100755** (có bit thực thi); mode **100644** báo không được ghi nhận là executable.

Khi review/commit, phạm vi file thông thường:

~~~bash
git add gradlew gradlew.bat gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties
git diff --cached --check
~~~

Đây là ví dụ chuẩn bị commit; chỉ commit khi các bước kiểm thử và chính sách review của dự án đã đạt. Không vô tình commit cache hoặc file chứa password.

## 4. Xác minh tính toàn vẹn và an toàn khi nâng cấp

### 4.1. Checksum distribution

Task wrapper với **--gradle-distribution-sha256-sum** ghi property **distributionSha256Sum**. Gradle Wrapper kiểm tra SHA-256 khi tải distribution chưa có trong cache. Nếu checksum không khớp, download bị từ chối.

Điểm cần hiểu:

- Kiểm tra checksum phải dùng giá trị lấy từ nguồn chính thức, độc lập với file ZIP tải xuống.
- **distributionSha256Sum** bảo vệ Gradle ZIP; nó **không** thay thế kiểm tra Wrapper JAR.
- Với ZIP đã tồn tại trong cache, không nên cho rằng việc chạy Wrapper lần nữa sẽ bắt buộc kiểm tra lại toàn bộ bản tải cũ. Khi đánh giá một incident liên quan cache, đối chiếu thủ công và chỉ xóa bản phân phối bị nghi ngờ sau khi xác định đúng thư mục.

### 4.2. Xác minh Wrapper JAR

Wrapper JAR chạy **trước** build script, nên cần xem nó như mã thực thi được đưa vào repository. Đối chiếu SHA-256 với bản Wrapper JAR chính thức trên **https://gradle.org/release-checksums/** hoặc file checksum được công bố của đúng phiên bản.

**Linux:**

~~~bash
sha256sum gradle/wrapper/gradle-wrapper.jar
~~~

**macOS:**

~~~bash
shasum -a 256 gradle/wrapper/gradle-wrapper.jar
~~~

**Windows PowerShell:**

~~~powershell
(Get-FileHash .\gradle\wrapper\gradle-wrapper.jar -Algorithm SHA256).Hash.ToLower()
~~~

Với ví dụ 9.9.0, checksum JAR chính thức được công bố tại:

~~~text
https://services.gradle.org/distributions/gradle-9.9.0-wrapper.jar.sha256
~~~

Khi so sánh, chú ý **wrapper JAR** và **distribution ZIP** là hai artifact khác nhau, có checksum khác nhau. Nếu JAR checksum khớp một phiên bản cũ vì mới chạy **:wrapper** một lần, chạy lần thứ hai sau khi kiểm chứng Gradle mới. Nếu checksum không khớp bất kỳ nguồn đáng tin nào, ngừng sử dụng JAR đó và điều tra nguồn thay đổi; không bỏ qua cảnh báo bảo mật.

## 5. Khắc phục lỗi quyền thực thi trên Linux/macOS

### 5.1. Permission denied

Ví dụ:

~~~text
$ ./gradlew --version
bash: ./gradlew: Permission denied
~~~

Lỗi thường do file **gradlew** không có bit execute, đặc biệt khi repo được tạo hoặc chỉnh qua Windows, ZIP hoặc hệ thống file không giữ permission của Unix.

Kiểm tra và sửa trong thư mục chứa **gradlew**:

~~~bash
ls -l gradlew
chmod +x gradlew
./gradlew --version
~~~

Phần quyền nên hiện dạng như **-rwxr-xr-x** nếu chính sách dự án cho phép. Không dùng **chmod 777**: mở quyền ghi không cần thiết, tạo rủi ro đối với script sẽ thực thi mã.

Để quyền tồn tại qua Git checkout và CI, kiểm tra Git index:

~~~bash
git ls-files -s gradlew
git update-index --chmod=+x gradlew
git ls-files -s gradlew
~~~

Kết quả mong muốn là mode **100755** thay vì **100644**. Sau đó đưa thay đổi mode vào commit theo quy trình của repo. **chmod +x** trên máy hiện tại và việc Git lưu execute bit là hai việc liên quan nhưng không đồng nhất.

### 5.2. Tránh nhầm với script Windows

- Linux/macOS: gọi **./gradlew** (trên POSIX shell, dấu **./** cho biết thực thi file trong thư mục hiện tại).
- Windows PowerShell: gọi **.\gradlew.bat**. PowerShell thường không tự tìm file trong current directory nếu chỉ gõ tên trần.
- Windows cmd.exe: có thể gọi **gradlew.bat** ngay tại thư mục dự án, hoặc dùng đường dẫn tương ứng.

Không dùng **chmod +x gradlew.bat** để xử lý lỗi trên Windows; file **.bat** không dựa trên Unix executable bit.

### 5.3. Lỗi CRLF / dấu ^M trong script shell

Script Unix cần line ending **LF**. Khi file **gradlew** bị đổi sang **CRLF**, lỗi có thể là:

~~~text
/bin/sh^M: bad interpreter
~~~

hoặc thông báo “No such file or directory” dù file vẫn tồn tại. **chmod +x** không sửa được line ending sai.

Kiểm tra:

~~~bash
file gradlew
head -n 1 gradlew
~~~

Nếu Git đang đổi line ending, quy ước **.gitattributes** nên giữ:

~~~gitattributes
gradlew text eol=lf
gradlew.bat text eol=crlf
~~~

Sau khi quy ước được review và áp dụng, có thể chuẩn hóa **đúng hai script này**:

~~~bash
git add --renormalize gradlew gradlew.bat
git diff --cached --check
~~~

Kiểm tra lại dữ liệu trong working tree trước khi chạy; với một số môi trường có thể cần checkout lại script để áp dụng line ending của Git. Đừng chuyển line ending bừa bãi cho tất cả file trong repository.

### 5.4. File hiện hữu nhưng vẫn không chạy

Nếu **./gradlew** báo không tìm được file:

1. Chạy **pwd** và **ls -l gradlew** để xác định thư mục hiện tại.
2. Kiểm tra shebang (dòng đầu) và line ending; một đường dẫn interpreter chứa ký tự CR có thể gây thông báo giống thiếu file.
3. Kiểm tra quyền execute của thư mục cha và chính sách mount, nhất là file system gắn **noexec**.
4. Nếu đang gọi lệnh từ subproject, dùng đường dẫn tương đối đúng như **../gradlew** hoặc chuyển về root; không tạo thêm Wrapper cho mỗi module nếu cả repo đã dùng Wrapper gốc.

Có thể thử **sh ./gradlew --version** để phân biệt vấn đề execute bit với lỗi khác, nhưng cách gọi này **không** thay thế việc sửa quyền trong Git/CI. Chỉ chạy script khi đã xác minh nó đến từ nguồn repo đáng tin.

## 6. Lỗi đường dẫn và Java/JDK

### 6.1. Bạn đang đứng ở thư mục nào?

Một lỗi phổ biến là gọi **./gradlew** trong thư mục không chứa script, hoặc IDE/terminal mở tại sai working directory.

Ví dụ repo đa module:

~~~text
repo/
├── gradlew
├── gradlew.bat
├── settings.gradle
├── gradle/wrapper/
└── service-a/
    └── build.gradle
~~~

Trong **repo/**:

~~~bash
./gradlew :service-a:build
~~~

Trong **repo/service-a/** có thể gọi script ở cha bằng **../gradlew**, nhưng trở về root giúp việc quan sát và xử lý đường dẫn rõ ràng hơn:

~~~bash
cd ..
./gradlew :service-a:build
~~~

Tên task/path cụ thể tùy cấu hình **settings.gradle**; **:service-a:build** chỉ đúng khi project **service-a** thực sự được include.

### 6.2. Phân biệt JAVA_HOME, PATH, GRADLE_HOME và GRADLE_USER_HOME

| Giá trị | Dùng để làm gì? | Dấu hiệu sai |
| --- | --- | --- |
| **JAVA_HOME** | Chỉ thư mục cài JDK được dùng để chọn Java khởi động (trừ khi có cơ chế cấu hình JVM khác phù hợp). | “JAVA_HOME is set to an invalid directory”; không chạy được Java. |
| **PATH** | Giúp shell tìm executable như **java** hay **git**. | **java: command not found** hoặc chạy nhầm JDK. |
| **GRADLE_HOME** | Thư mục Gradle được cài thủ công nếu có. | Lệnh **gradle** toàn cục sai phiên bản; không nên dùng nó thay Wrapper. |
| **GRADLE_USER_HOME** | Nơi Gradle lưu config người dùng, cache, distribution tải bởi Wrapper, log. | Không ghi được cache, tải lại liên tục hoặc thiếu proxy config đang kỳ vọng. |
| **Project root** | Nơi chứa **settings.gradle(.kts)**, **gradlew**, các build script. | Chạy nhầm project/task hoặc không tìm được Wrapper. |

Vị trí **GRADLE_USER_HOME** mặc định thường là **~/.gradle** (Linux/macOS) hoặc **C:\Users\<tài-khoản>\.gradle** (Windows). Đây không phải **./.gradle** trong project; hai vị trí có mục đích khác nhau.

**Linux/macOS:**

~~~bash
java -version
printf 'JAVA_HOME=%s\n' "$JAVA_HOME"
printf 'GRADLE_USER_HOME=%s\n' "$GRADLE_USER_HOME"
command -v java
./gradlew --version
~~~

**Windows PowerShell:**

~~~powershell
java -version
$env:JAVA_HOME
$env:GRADLE_USER_HOME
Get-Command java
.\gradlew.bat --version
~~~

Nếu **JAVA_HOME** sai, trỏ nó về **thư mục gốc JDK**, không phải thư mục **bin** hay file **java.exe**. Đường dẫn cài JDK thực tế khác nhau giữa máy; kiểm tra đường dẫn đã tồn tại trước khi cấu hình môi trường.

Khi cần tách cache CI hoặc muốn chẩn đoán Gradle User Home hiện tại, có thể chọn một thư mục riêng cho **phiên terminal**:

**Bash:**

~~~bash
export GRADLE_USER_HOME="$HOME/.gradle-wrapper-lab"
./gradlew --version
~~~

**PowerShell:**

~~~powershell
$env:GRADLE_USER_HOME = Join-Path $env:USERPROFILE '.gradle-wrapper-lab'
.\gradlew.bat --version
~~~

Hãy nhớ cấu hình proxy, repository hoặc credentials đặt trong **GRADLE_USER_HOME** cũ sẽ **không tự chuyển** sang vị trí mới. Đây là kỹ thuật cô lập môi trường để kiểm tra, không phải lý do để xóa toàn bộ cache cũ.

### 6.3. Đường dẫn có dấu cách hoặc ký tự đặc biệt

Windows thường cài JDK ở đường dẫn có dấu cách như **Program Files**. Khi chạy trực tiếp một file bằng đường dẫn đầy đủ trong PowerShell, dùng toán tử gọi **&** và dấu nháy:

~~~powershell
& '.\gradlew.bat' --version
~~~

Tại project có đường dẫn chứa dấu cách, vẫn gọi **.\gradlew.bat** sau khi chuyển đến đúng thư mục. Không tự sửa script Wrapper chỉ để “khắc phục khoảng trắng”; script sinh bởi Gradle đã xử lý các trường hợp đường dẫn chuẩn.

### 6.4. JDK chạy Gradle khác Java toolchain

Ví dụ **build.gradle** có:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Cấu hình này yêu cầu **Java 17 toolchain để biên dịch**; nó **không tự hạ** JDK đang khởi động bản Gradle mới. Khi gặp thông báo Java runtime không tương thích hoặc **Unsupported class file major version**, kiểm tra cả phiên bản JDK đang chạy Gradle, phiên bản Gradle được chọn và plugin được áp dụng. Đọc release notes/compatibility matrix trước khi sửa.

## 7. Wrapper hoạt động sau proxy như thế nào?

### 7.1. Phân biệt các đích mạng

Trong môi trường doanh nghiệp, có thể có các đích:

- **services.gradle.org**: tải Gradle distribution theo **distributionUrl** mặc định.
- **plugins.gradle.org** hoặc plugin repository nội bộ: giải quyết Gradle plugins.
- **repo.maven.apache.org** hoặc Maven repository nội bộ: tải dependency Java.
- **Mirror** được doanh nghiệp quản lý: phân phối Gradle hoặc dependencies qua mạng nội bộ.

Một proxy có thể cho phép truy cập repository nội bộ nhưng chặn Internet công cộng. Do đó **./gradlew --version** có thể thành công nhờ đã cache distribution, trong khi **./gradlew build** vẫn lỗi tải dependency; hoặc ngược lại, build chưa kịp khởi động vì distribution chưa được tải.

### 7.2. Cấu hình HTTP/HTTPS proxy bằng JVM system properties

Gradle dùng các **JVM system properties** để cấu hình proxy. Với thiết lập cá nhân, nơi nên đặt là:

~~~text
Linux/macOS: ~/.gradle/gradle.properties
Windows:     %USERPROFILE%\.gradle\gradle.properties
~~~

Nếu **GRADLE_USER_HOME** được đổi, dùng file **gradle.properties** bên trong thư mục đó.

Ví dụ cấu hình **không chứa tài khoản hoặc mật khẩu**; tên **proxy.example.org** là domain minh họa, cần thay bằng địa chỉ proxy do mạng của bạn cung cấp:

~~~properties
systemProp.http.proxyHost=proxy.example.org
systemProp.http.proxyPort=8080

systemProp.https.proxyHost=proxy.example.org
systemProp.https.proxyPort=8080

systemProp.http.nonProxyHosts=localhost|127.*|*.internal.example.org
~~~

Giải thích:

- **http.proxyHost / http.proxyPort** dành cho kết nối HTTP qua proxy.
- **https.proxyHost / https.proxyPort** dành cho kết nối HTTPS qua proxy.
- **http.nonProxyHosts** là danh sách host được phép đi trực tiếp, phân cách bằng ký tự **|**; tài liệu Gradle dùng property này cho ví dụ HTTPS nữa. Điều chỉnh danh sách theo chính sách mạng thực tế.
- Port **8080** chỉ là ví dụ. Proxy thực tế có thể dùng port khác; không suy đoán port từ việc trang đích sử dụng HTTPS.

File cấu hình ở **user home** áp dụng theo người dùng, hữu ích để không đưa proxy cá nhân hoặc secret vào source repo. Trong multi-project Gradle, các **systemProp.*** được khai báo trong **gradle.properties** của root project mới được xét theo quy tắc tương ứng; file **gradle.properties** ở subproject không phải chỗ đáng tin để đặt toàn bộ cấu hình proxy.

Các biến shell **HTTP_PROXY**, **HTTPS_PROXY** hoặc **NO_PROXY** không bảo đảm được Wrapper/Gradle đọc giống **curl** hay trình duyệt. Khi curl hoạt động mà Gradle báo timeout, kiểm tra **JVM proxy properties** và môi trường Java được chạy thay vì chỉ nhìn các biến môi trường của shell.

### 7.3. Proxy có xác thực

Nếu proxy yêu cầu username/password, các property JVM liên quan là **http.proxyUser**, **http.proxyPassword**, **https.proxyUser**, **https.proxyPassword**; với proxy kiểu NTLM đôi khi cần thêm domain theo tài liệu mạng của Gradle/JDK.

Không ghi mật khẩu proxy trực tiếp vào file **gradle.properties** đã commit, script Wrapper, URL công khai hoặc build log. Ngay cả file trong user home cũng có rủi ro nếu người khác đọc được; dùng cơ chế cung cấp credential được doanh nghiệp hỗ trợ, giới hạn quyền đọc và không in secret vào terminal/log.

**Proxy authentication** khác với **distribution server authentication**:

- Proxy yêu cầu xác thực để chuyển tiếp yêu cầu ra ngoài.
- Server nội bộ chứa Gradle ZIP có thể yêu cầu Basic/Bearer authentication **sau** khi kết nối qua proxy thành công.

Gradle Wrapper hỗ trợ các thuộc tính xác thực server như **gradle.wrapperUser**, **gradle.wrapperPassword** hoặc token có scope theo hostname. Nếu cần, cấu hình cho **đúng máy chủ được tin cậy**, dùng HTTPS và tránh nhúng username/password vào **distributionUrl** sẽ được commit vào Git. Nhầm hai lớp xác thực thường dẫn đến cấu hình đúng proxy nhưng vẫn gặp HTTP 401.

### 7.4. Timeout, retries và mirror nội bộ

Khi đường truyền chậm, Wrapper cho phép cấu hình thời gian chờ và số lần retry. Ví dụ trong **gradle/wrapper/gradle-wrapper.properties** (minh họa các khóa, những property URL/checksum hiện có vẫn cần được giữ):

~~~properties
networkTimeout=30000
retries=3
retryBackOffMs=1000
~~~

**networkTimeout** dùng mili giây. **retries=3** yêu cầu thử lại khi tải Gradle distribution gặp lỗi có thể retry; **retryBackOffMs** là khoảng chờ ban đầu. Các giá trị này **không** sửa lỗi HTTP 407, sai credentials, thiếu trust certificate hoặc URL 404.

Nếu tổ chức dùng Gradle mirror riêng, task **:wrapper** có tùy chọn **--gradle-distribution-url** để cấu hình URL của ZIP được phục vụ nội bộ. Chỉ sử dụng URL HTTPS được phê duyệt, checksum tương ứng và kiểm tra rằng server hỗ trợ cơ chế xác thực/HEAD request theo chính sách. Đừng đổi tên distribution hoặc trộn checksum của ZIP khác.

**--offline** không phải giải pháp để “tải vượt proxy”: khi chưa có Gradle distribution hoặc dependency cần thiết trong cache, offline không thể tạo ra những tệp đó.

### 7.5. TLS và chứng chỉ

Lỗi dạng:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

thường liên quan tới Java truststore hoặc chứng chỉ TLS do proxy/corporate gateway cung cấp. Cần xác minh chain chứng chỉ, JDK đang dùng và CA được cấp phát cho doanh nghiệp; nếu cần, import CA được tin cậy theo quy trình IT và dùng truststore đúng JVM.

Không giải quyết lỗi TLS bằng cách tắt kiểm tra chứng chỉ, đổi sang HTTP không mã hóa hoặc chấp nhận JAR/ZIP không rõ nguồn. Việc **curl** kết nối thành công không bảo đảm truststore của JVM có cùng CA/cấu hình mạng.

## 8. Bài thực hành có thể chạy: kiểm chứng Wrapper sau nâng cấp

Mục tiêu là dùng một project Java 17 cực nhỏ để thấy rõ **Wrapper khởi động đúng phiên bản**, task Java hoạt động và chương trình chạy được. Cần JDK đáp ứng yêu cầu của Gradle được chọn và Java 17 toolchain đã có hoặc được cung cấp qua cơ chế được cấu hình.

### 8.1. Cấu trúc

~~~text
wrapper-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/gradle-wrapper.jar
├── gradle/wrapper/gradle-wrapper.properties
└── src/main/java/example/WrapperDemo.java
~~~

File Wrapper có thể được sinh bằng **gradle :wrapper** trên máy đã cài Gradle rồi nâng cấp theo mục 3. Các file nguồn như sau.

**settings.gradle**

~~~groovy
rootProject.name = 'wrapper-lab'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

**src/main/java/example/WrapperDemo.java**

~~~java
package example;

public final class WrapperDemo {
    private WrapperDemo() {
    }

    public static void main(String[] args) {
        System.out.println("Gradle Wrapper OK");
    }
}
~~~

Java class và file trùng tên; package **example** khớp thư mục **src/main/java/example/**. Chương trình chỉ dùng Java standard library và không cần dependency ngoài.

### 8.2. Chạy bằng Wrapper

**Linux/macOS:**

~~~bash
./gradlew --version
./gradlew clean build
java -cp build/classes/java/main example.WrapperDemo
~~~

**Windows PowerShell:**

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean build
java -cp .\build\classes\java\main example.WrapperDemo
~~~

Dòng stdout **chính xác của chương trình Java**:

~~~text
Gradle Wrapper OK
~~~

Gradle sẽ in thêm log task, thời gian build và trạng thái cache khác nhau tùy môi trường. Kỳ vọng **./gradlew --version** hiển thị đúng version đã cấu hình và **build** kết thúc bằng **BUILD SUCCESSFUL**; không gán số lượng task hay thời gian cố định. Câu lệnh **java -cp** được chạy sau build thành công; với JDK 17 trở lên, source class ví dụ có thể chạy theo lệnh trên.

Có thể biên dịch/chạy riêng bằng JDK mà không cần Gradle để đối chiếu phần Java:

~~~bash
javac -d out src/main/java/example/WrapperDemo.java
java -cp out example.WrapperDemo
~~~

Kết quả stdout vẫn là **Gradle Wrapper OK**. Cách chạy này chứng minh chương trình Java đúng; nó **không** xác minh khả năng tải Gradle distribution, cấu hình plugin hoặc task build, vì vậy kiểm thử Wrapper vẫn phải dùng **./gradlew**.

### 8.3. Ba tình huống quan sát

1. **Chạy lần đầu trên máy sạch:** Wrapper cần tải Gradle ZIP nên xuất hiện log download; Gradle sau đó compile chương trình.
2. **Chạy lần hai khi cache còn hợp lệ:** Wrapper có thể sử dụng Gradle distribution đã tải, task Java có thể được báo **UP-TO-DATE**; điều này thường bình thường.
3. **CI Linux báo Permission denied:** kiểm tra file mode **100755** của **gradlew** và line ending **LF** trong Git thay vì sửa logic **WrapperDemo.java**.

## 9. Bảng chẩn đoán lỗi theo dấu hiệu

| Dấu hiệu | Lớp lỗi nên kiểm tra trước | Cách kiểm chứng/xử lý |
| --- | --- | --- |
| **./gradlew: Permission denied** | Execute bit/file system Unix | **ls -l gradlew**, **chmod +x gradlew**, **git ls-files -s gradlew**; kiểm tra mount **noexec** nếu cần. |
| **/bin/sh^M: bad interpreter** | CRLF trên shell script | Kiểm tra **file gradlew**, giữ **gradlew** dạng LF qua **.gitattributes**. |
| **gradlew: command not found** | Shell/path | Đứng tại root và gọi **./gradlew**, không gọi tên trần trên POSIX shell. |
| **'.\gradlew.bat' is not recognized** | Sai thư mục, thiếu file hoặc cú pháp gọi Windows | **Get-Location**, **Get-ChildItem .\gradlew*** rồi gọi **.\gradlew.bat**. |
| **Could not find or load main class org.gradle.wrapper.GradleWrapperMain** | **gradle-wrapper.jar** bị thiếu/hỏng hoặc classpath bootstrap sai | Kiểm tra file JAR từ Git và checksum chính thức; khôi phục từ nguồn tin cậy hoặc sinh lại bằng Gradle CLI phù hợp. |
| **JAVA_HOME is set to an invalid directory** | Đường dẫn JDK | Kiểm tra **JAVA_HOME**, JDK root, **java -version** và đường dẫn thật của Java. |
| **Gradle requires Java ... / Unsupported class file major version** | Không tương thích Gradle/JDK/plugin | So yêu cầu JDK của Gradle mới, plugin và toolchain; chọn phiên bản tương thích. |
| **Read timed out / Connect timed out** | Mạng, DNS, firewall, proxy, server | Phân biệt đang tải distribution hay dependency; kiểm tra host/port/proxy; timeout/retry chỉ hỗ trợ mạng chậm. |
| **HTTP 407 Proxy Authentication Required** | Xác thực tại proxy | Xác minh proxy host/port, quyền truy cập và cách cấp credential proxy; không sửa repository Maven thay cho proxy. |
| **HTTP 401 Unauthorized** | Xác thực server/repository | Xác định URL bị từ chối: server phân phối Gradle hay Maven/plugin repository; cấu hình credential đúng host. |
| **PKIX path building failed** | TLS/JVM truststore | Kiểm tra chứng chỉ CA của proxy, JDK và truststore; không vô hiệu hóa xác thực TLS. |
| **HTTP 404 khi tải Gradle ZIP** | Sai version, distribution URL hoặc mirror | Kiểm tra chính xác tên bản **-bin/-all**, URL HTTPS và phiên bản tồn tại. |
| **Checksum verification failed** | ZIP khác checksum, tải hỏng hoặc artifact bị thay đổi | Dừng và đối chiếu checksum chính thức với URL/version; kiểm tra cache/mirror; không tắt xác minh để chạy tiếp. |
| **Could not resolve dependencies/plugin** | Repository/plugin management, mạng sau bootstrap | Wrapper đã khởi động; kiểm tra **repositories**, **pluginManagement**, proxy và repository credentials. |
| **Access denied vào .gradle/cache** | Quyền ghi, file lock, antivirus hoặc user profile | Kiểm tra thư mục **GRADLE_USER_HOME**, quyền tài khoản và tiến trình đang giữ lock; giới hạn thao tác vào đúng phần lỗi. |

### 9.1. Trình tự điều tra giúp tránh sửa sai chỗ

~~~text
1. Có tìm thấy đúng script gradlew / gradlew.bat?
      |
      +-- Không: sửa thư mục làm việc/đường dẫn/file thiếu.
      |
      v
2. Script khởi động được JVM?
      |
      +-- Không: quyền execute, CRLF, JAVA_HOME/JDK.
      |
      v
3. Wrapper tải/khởi chạy đúng Gradle distribution?
      |
      +-- Không: distributionUrl, checksum, DNS/proxy/TLS/cache.
      |
      v
4. Gradle cấu hình được project?
      |
      +-- Không: plugin compatibility, settings/build script,
      |          plugin repository, JDK runtime.
      |
      v
5. Gradle chạy compile/test/build?
      |
      +-- Không: toolchain, dependency repository, test/source.
      |
      v
6. Chạy đúng bản Gradle và toàn bộ quality gate đạt.
~~~

Việc phân tầng đặc biệt hữu ích khi log dài. Nhìn **dòng lỗi đầu tiên có nguyên nhân thực sự** và URL đang được tải: lỗi của Wrapper launcher khác với lỗi Gradle đã khởi động rồi mới cấu hình project.

## 10. Khôi phục nâng cấp lỗi và tránh phá cache

Nếu upgrade thất bại, hãy xác định **mốc thành công cuối cùng**: (1) trước khi đổi properties, (2) sau lần chạy :wrapper đầu, (3) sau khi Wrapper tải Gradle mới, hay (4) sau khi plugin/build thực thi.

Các bước phù hợp:

1. Giữ lại log lỗi đủ để phân biệt quyền, Java, mạng và tương thích plugin.
2. Nếu tính tương thích chưa đạt, quay về các file Wrapper đã được **review và version-control** theo chính sách Git của repo. Nếu có thay đổi cá nhân khác cùng file, phải tách/giữ phần đó trước khi khôi phục; không dùng lệnh reset hàng loạt làm mất công việc.
3. Chạy lại **Wrapper --version** và **help/build** trên phiên bản đã biết hoạt động để xác định baseline thực sự được phục hồi.
4. Nếu cần nâng theo nhiều bước vì Gradle/plugin quá cũ, chọn các version trung gian có hỗ trợ được xác nhận và kiểm thử từng bước.
5. Nếu nghi ZIP cache hỏng, tìm chính xác thư mục distribution tương ứng dưới **GRADLE_USER_HOME/wrapper/dists/** và chỉ xử lý bản bị lỗi sau khi đã kiểm tra đường dẫn thực. Không xóa nguyên thư mục **~/.gradle** hoặc **build/** tùy tiện để che lỗi gốc.

**Dấu hiệu đáng quan sát trên Git:** một commit upgrade chỉ đổi **gradle-wrapper.properties** nhưng không đổi **gradle-wrapper.jar** có thể là do chỉ chạy **:wrapper** một lần. Đừng kết luận sai ngay rằng build không hoạt động; hãy đồng bộ đầy đủ bằng lần chạy thứ hai và thực hiện checksum verification trước khi merge.

## 11. Checklist hoàn tất cho developer và CI

| Cổng kiểm tra | Điều kiện đạt |
| --- | --- |
| **Phiên bản** | Wrapper báo đúng version mục tiêu; **distributionUrl** là URL được duyệt, đúng **-bin/-all**. |
| **Tính toàn vẹn** | **distributionSha256Sum** khớp bản ZIP; **gradle-wrapper.jar** được xác thực theo checksum/nguồn chính thức. |
| **File trong Git** | Có đủ **gradlew**, **gradlew.bat**, Wrapper JAR và properties; **gradlew** mode **100755**, line ending LF. |
| **Khả năng chạy đa nền tảng** | Linux/macOS gọi **./gradlew**, Windows gọi **.\gradlew.bat**; path và quyền thực thi đúng. |
| **Java** | JDK chạy Gradle đáp ứng yêu cầu bản mới; toolchain biên dịch phù hợp module. |
| **Mạng** | Distribution, plugin và dependencies truy cập được qua proxy/mirror, với TLS và credential đúng scope. |
| **Chất lượng** | Baseline và build/test đã chạy sau upgrade; lỗi tương thích plugin được xử lý. |
| **Review** | Kiểm tra diff bốn file, không lộ secret, không commit cache; CI chạy cùng Wrapper. |

Trong CI, nên dùng Wrapper từ checkout của chính commit được build, kiểm tra checksum Wrapper JAR bằng cơ chế được hỗ trợ, cài JDK phù hợp, rồi chạy các quality gate. Một pipeline **không nên** phụ thuộc vào bản Gradle toàn cục tình cờ có sẵn trên runner.

## 12. Câu hỏi củng cố và bài tập

**Câu 1.** Đổi **distributionUrl** từ một phiên bản sang bản mới có đủ để khẳng định toàn bộ Wrapper đã được nâng cấp chưa?

**Câu 2.** Trên Windows chạy được **gradlew.bat**, lên Linux gặp **Permission denied**. Nên sửa source Java, nâng Gradle hay kiểm tra điều gì trước?

**Câu 3.** Proxy đã được khai báo trong biến môi trường **HTTPS_PROXY**, nhưng Wrapper vẫn timeout. Vì sao cần kiểm tra **systemProp.https.proxyHost**?

**Câu 4.** Lệnh **./gradlew --version** thành công, **./gradlew build** thất bại với lỗi dependency. Lỗi ở lớp nào?

**Câu 5.** Khi nghi vấn lỗi checksum ZIP, vì sao không nên tắt kiểm tra SHA-256 chỉ để build qua?

**Đáp án gợi ý:**

1. **Chưa.** Chạy **:wrapper** lần thứ hai bằng Gradle mới, kiểm tra đủ JAR/script/properties và chạy build.
2. Kiểm tra **gradlew** executable bit trong filesystem và Git (**100755**), cùng line ending **LF**.
3. Gradle/Wrapper dùng cơ chế proxy của JVM; biến shell được curl/trình duyệt hiểu không bảo đảm được Java tự sử dụng.
4. Distribution/bootstrap đã hoạt động; kiểm tra mạng, proxy, repository hoặc credential ở giai đoạn giải quyết dependency/plugin.
5. Checksum phát hiện ZIP bị sai, hỏng hoặc không đáng tin; phải xác minh version, nguồn và cache trước khi thực thi artifact.

**Bài tập thực hành:** tạo project **wrapper-lab**, chuẩn bị Wrapper, nâng đúng một phiên bản tương thích với JDK và plugin, kiểm tra **./gradlew --version**, chạy **build**, đối chiếu Git execute bit, sau đó mô tả điều gì thay đổi giữa hai lần chạy **:wrapper** và nơi đặt cấu hình proxy user-level. Thử chẩn đoán theo mục 9 nếu môi trường không có kết nối Internet: phân biệt “chưa tải Gradle ZIP” với “Gradle đã chạy nhưng thiếu dependency”.

## 13. Tài liệu chính thức

- [Gradle Wrapper — thêm, dùng và nâng cấp](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Wrapper Basics — các file Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper_basics.html)
- [Networking with Gradle — cấu hình HTTP/HTTPS proxy](https://docs.gradle.org/current/userguide/networking.html)
- [Build Environment Configuration — property, JAVA_HOME và GRADLE_USER_HOME](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html)
- [Gradle Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Gradle Release Checksums](https://gradle.org/release-checksums/)

Một lần nâng cấp Wrapper đạt chất lượng là một lần **nâng có chủ đích, xác minh được, chạy được trên nhiều máy và có đường khôi phục**. Nắm vững ranh giới giữa script, JDK, Gradle distribution, repository và proxy giúp giải quyết đúng nguyên nhân, giữ build ổn định từ laptop đến CI.
