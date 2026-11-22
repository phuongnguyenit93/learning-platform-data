# Ổn định timestamp trong build Java

## 1. Timestamp ổn định là gì?

Trong một quy trình build, timestamp có thể được ghi vào metadata của file trong JAR/ZIP, manifest, resource được generate, file build-info hoặc log của build tool. Nếu timestamp được lấy trực tiếp từ đồng hồ máy chạy build, hai lần build cùng một source revision có thể tạo ra artifact khác nhau chỉ vì được chạy ở thời điểm khác nhau.

Ổn định timestamp là đặt một giá trị thời gian xác định cho metadata cần đóng gói, để cùng source và cùng cấu hình có thể tạo ra artifact giống nhau qua nhiều lần build.

Mục tiêu thường gặp:

- JAR được tạo lại có cùng timestamp cho mọi entry.
- Build trên hai máy không bị lệch timestamp vì timezone hoặc filesystem mtime.
- Hash SHA-256 của artifact không đổi khi chỉ thời gian build thay đổi.
- Timestamp dùng trong manifest hoặc generated resource phản ánh một mốc ổn định của source revision.
- CI có thể so sánh artifact độc lập giữa các lần chạy.

Timestamp ổn định là một phần của reproducible build. Chỉ chuẩn hóa thời gian chưa đủ để bảo đảm toàn bộ artifact giống nhau; thứ tự file, compiler, dependency, nội dung manifest và generated resource cũng cần ổn định.

## 2. Phân biệt các loại timestamp

Không phải mọi timestamp đều ảnh hưởng tới hash của JAR theo cùng một cách.

| Loại thời gian | Nơi lưu | Có ảnh hưởng trực tiếp tới byte của JAR? |
|---|---|---|
| Source file mtime | Filesystem của source `.java` | Không tự động; compiler thường không chép mtime vào bytecode. |
| Class file mtime | Filesystem của `.class` | Không, trừ khi build tool đưa mtime đó vào archive. |
| Archive entry timestamp | Metadata ZIP của từng file trong JAR | Có; nó là một phần của archive. |
| JAR file mtime | Filesystem của file `.jar` sau khi tạo | Không thuộc nội dung byte của JAR, nên không ảnh hưởng SHA-256 của file. |
| Embedded build timestamp | Manifest, properties, JSON, generated source/resource | Có; timestamp là nội dung thực của artifact. |
| Build log timestamp | Console hoặc log file bên ngoài artifact | Không, trừ khi log được đóng gói vào artifact. |

`jar --list --verbose` hiển thị thời gian của từng entry bên trong archive. Đây là timestamp cần chuẩn hóa nếu muốn JAR byte-for-byte giống nhau.

Trong khi đó, `Get-Item app.jar | Select-Object LastWriteTime` hiển thị thời gian file JAR trên filesystem. Giá trị này có thể khác sau mỗi lần build mà hash của nội dung JAR vẫn giống hệt nhau.

## 3. Timestamp làm artifact thay đổi như thế nào?

JAR là một archive dựa trên ZIP. Mỗi entry có metadata, bao gồm thời gian sửa đổi. Nếu hai lần tạo JAR ghi cùng class file nhưng dùng thời điểm khác nhau, các trường timestamp trong ZIP khác nhau và hash toàn file cũng khác.

Ví dụ:

~~~text
Build lần 1:
com/example/Main.class  2026-11-10 20:00:00

Build lần 2:
com/example/Main.class  2026-11-10 21:00:00
~~~

Nội dung `Main.class` có thể giống nhau, nhưng metadata archive khác nhau.

Vì vậy, chỉ chạy `javac` với cùng source không bảo đảm JAR giống nhau. Cần chuẩn hóa timestamp tại bước đóng gói và kiểm tra các plugin tạo metadata bổ sung.

## 4. SOURCE_DATE_EPOCH

`SOURCE_DATE_EPOCH` là quy ước môi trường phổ biến trong reproducible build. Giá trị là số giây Unix tính từ `1970-01-01T00:00:00Z`.

Ví dụ:

~~~bash
SOURCE_DATE_EPOCH=1577836800
~~~

Giá trị trên tương ứng với:

~~~text
2020-01-01T00:00:00Z
~~~

Dùng một giá trị ổn định cho cùng source revision. Một cách phổ biến là lấy committer timestamp của Git commit:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct HEAD)"
~~~

Trên PowerShell:

~~~powershell
$env:SOURCE_DATE_EPOCH = (git log -1 --format=%ct HEAD).Trim()
~~~

`%ct` trả về committer date dưới dạng Unix seconds. Nếu hai build dùng cùng commit, giá trị này không phụ thuộc giờ máy chạy CI.

Không thay `SOURCE_DATE_EPOCH` bằng thời gian hiện tại như `date +%s` ở mỗi lần build; làm vậy sẽ tạo một timestamp khác cho mỗi lần chạy và phá tính lặp lại.

Nếu pipeline không có Git metadata, có thể truyền epoch đã được lưu trong release metadata hoặc source archive.

## 5. Đặt timestamp khi tạo JAR bằng jar

JDK cung cấp option `--date` cho lệnh `jar`:

~~~bash
jar --create --date=2020-01-01T00:00:00Z --file build/app.jar -C build/classes .
~~~

`--date` nhận timestamp ISO-8601 extended offset date-time. Nên chỉ định timezone rõ ràng, ví dụ hậu tố `Z` cho UTC.

Có thể dùng timestamp lấy từ `SOURCE_DATE_EPOCH`. Trên PowerShell:

~~~powershell
$timestamp = [DateTimeOffset]::FromUnixTimeSeconds(
    [long]$env:SOURCE_DATE_EPOCH
).UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")

jar --create "--date=$timestamp" --file build/app.jar -C build/classes .
~~~

Trên shell có GNU `date`:

~~~bash
timestamp="$(date -u -d "@$SOURCE_DATE_EPOCH" +'%Y-%m-%dT%H:%M:%SZ')"

jar --create "--date=$timestamp" --file build/app.jar -C build/classes .
~~~

`jar` không tự đọc `SOURCE_DATE_EPOCH`. Chỉ export biến môi trường rồi gọi `jar` không làm timestamp của entry thay đổi; cần chuyển epoch sang ISO timestamp và truyền qua `--date`.

`--date` áp dụng khi tạo hoặc cập nhật archive. Nó chuẩn hóa thời gian entry, nhưng không tự bảo đảm thứ tự file, nội dung manifest hoặc nội dung generated resource cũng ổn định.

## 6. Giữ thứ tự entry ổn định khi gọi jar

Hai JAR có cùng entry và cùng timestamp vẫn có thể khác hash nếu thứ tự entry trong archive khác nhau.

Khi gọi `jar` trực tiếp, hãy truyền file theo thứ tự xác định. Ví dụ:

~~~bash
jar --create \
  --date=2020-01-01T00:00:00Z \
  --file=build/app.jar \
  -C build/classes com/example/Greeting.class \
  -C build/classes com/example/Main.class
~~~

Với project lớn, tạo danh sách file theo thứ tự sắp xếp ổn định rồi truyền qua argument file `@file`. Không phụ thuộc thứ tự duyệt thư mục ngẫu nhiên của script hoặc filesystem.

Kiểm tra archive:

~~~bash
jar --list --verbose --file build/app.jar
~~~

Đầu ra cho biết timestamp và đường dẫn entry trong JAR. Nếu cần điều tra khác biệt, giải nén hai archive và so sánh danh sách entry, metadata và nội dung từng file.

## 7. Ổn định timestamp trong Maven

Maven dùng property `project.build.outputTimestamp` để truyền mốc thời gian ổn định cho các plugin hỗ trợ reproducible archive.

Đặt timestamp cố định trong `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>2020-01-01T00:00:00Z</project.build.outputTimestamp>
</properties>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</build>
~~~

`maven-jar-plugin` từ phiên bản 3.2.0 hỗ trợ `outputTimestamp`; mặc định tham số này lấy từ `${project.build.outputTimestamp}`.

Build:

~~~bash
mvn -B clean package
~~~

Maven Archiver dùng timestamp này cho các entry được đóng gói trong JAR. Khi dùng plugin khác như shade, assembly hoặc plugin tạo archive bổ sung, cần kiểm tra plugin đó có hỗ trợ reproducible output và có nhận cùng timestamp hay không.

Không nên chỉ cấu hình JAR plugin rồi kết luận toàn bộ artifact của một multi-module build đã reproducible. Mỗi plugin tạo archive hoặc generated file cần được kiểm tra riêng.

## 8. Đưa SOURCE_DATE_EPOCH vào Maven

Có thể lấy timestamp từ môi trường CI thay vì hard-code trong POM:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.outputTimestamp>${env.SOURCE_DATE_EPOCH}</project.build.outputTimestamp>
</properties>
~~~

CI đặt biến trước khi gọi Maven:

~~~bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct HEAD)"
mvn -B clean package
~~~

Maven JAR Plugin chấp nhận giá trị `outputTimestamp` dưới dạng ISO-8601 hoặc số nguyên Unix seconds. Vì vậy, giá trị epoch từ `SOURCE_DATE_EPOCH` có thể được truyền trực tiếp.

Có thể truyền qua command line:

~~~bash
mvn -B "-Dproject.build.outputTimestamp=$SOURCE_DATE_EPOCH" clean package
~~~

Nếu biến môi trường không được thiết lập, property `${env.SOURCE_DATE_EPOCH}` có thể không được resolve thành timestamp hợp lệ. Hãy bảo đảm CI luôn cấp biến trước bước package hoặc dùng một giá trị mặc định có chủ đích.

## 9. Ổn định archive timestamp trong Gradle

Gradle cung cấp hai thuộc tính cho archive task:

- `preserveFileTimestamps`: có giữ mtime của file nguồn bên trong archive hay không.
- `reproducibleFileOrder`: có duyệt file theo thứ tự ổn định hay không.

Cấu hình rõ ràng cho JAR:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Khi `preserveFileTimestamps = false`, Gradle chuẩn hóa timestamp của entry thay vì giữ thời gian sửa đổi của file trên filesystem. Khi `reproducibleFileOrder = true`, Gradle duyệt các file trong archive theo thứ tự ổn định, không phụ thuộc thứ tự trả về của filesystem.

Từ Gradle 9.0, hai thuộc tính này mặc định lần lượt là `false` và `true` đối với archive task. Vẫn nên khai báo rõ trong build file để ý định của dự án dễ review và không phụ thuộc vào mặc định của phiên bản cũ.

Chạy:

~~~bash
gradle clean jar
~~~

Kiểm tra:

~~~bash
jar --list --verbose --file build/libs/gradle-1.0.0.jar
~~~

Gradle dùng một timestamp ZIP-compatible đã chuẩn hóa cho các entry. Cấu hình này ưu tiên byte-for-byte reproducible archive; nó không tự chọn timestamp của Git commit.

## 10. Không nhúng thời gian build hiện tại vào manifest

Dù archive entry đã được chuẩn hóa, JAR vẫn có thể khác nhau nếu manifest chứa timestamp động.

Ví dụ không phù hợp cho reproducible build:

~~~xml
<manifestEntries>
    <Build-Time>${maven.build.timestamp}</Build-Time>
</manifestEntries>
~~~

`maven.build.timestamp` thay đổi theo thời điểm chạy Maven. Vì manifest nằm bên trong JAR, giá trị đó làm thay đổi nội dung artifact.

Nếu cần metadata thời gian, hãy dùng cùng nguồn timestamp ổn định:

~~~xml
<manifestEntries>
    <Build-Revision-Time>${project.build.outputTimestamp}</Build-Revision-Time>
</manifestEntries>
~~~

Cần phân biệt giá trị ISO-8601 và epoch seconds. Nếu manifest yêu cầu định dạng dễ đọc, chuyển epoch sang ISO UTC bằng một bước xác định trước khi đưa vào manifest.

Với Gradle, tránh tạo manifest entry từ `new Date()` hoặc `System.currentTimeMillis()`. Nếu cần ghi revision time, lấy giá trị từ metadata của source revision và bảo đảm nó không đổi giữa các lần build cùng revision.

## 11. Generated resource và build-info file

Một số plugin tạo `build-info.properties`, `git.properties`, version file hoặc JSON chứa thời gian build. Những file này cũng được đóng gói vào JAR.

Ví dụ một resource:

~~~properties
build.version=1.0.0
build.time=2026-11-10T21:00:00Z
build.revision=abc123
~~~

Nếu `build.time` lấy từ đồng hồ hiện tại, hai lần build cùng commit sẽ tạo resource khác nhau.

Để ổn định:

- Dùng `SOURCE_DATE_EPOCH` hoặc commit timestamp đã được pin.
- Chuẩn hóa timezone về UTC.
- Không ghi millisecond/nanosecond nếu nguồn timestamp chỉ có độ chính xác tới giây.
- Cấu hình plugin tạo build-info dùng cùng timestamp.
- Kiểm tra generated file sau build và so sánh hash.
- Không đưa thời gian của CI job hoặc thời gian deploy vào artifact build nếu không cần thiết.

Timestamp runtime như thời gian ứng dụng khởi động vẫn có thể được log khi ứng dụng chạy. Điều cần tránh là ghi thời gian chạy build vào nội dung artifact khi muốn artifact reproducible.

## 12. Timezone và định dạng timestamp

Một mốc thời gian nên có biểu diễn thống nhất trên mọi máy build.

Khuyến nghị:

~~~text
2020-01-01T00:00:00Z
~~~

`Z` biểu thị UTC. Nếu dùng offset khác, hãy ghi rõ offset:

~~~text
2020-01-01T07:00:00+07:00
~~~

Hai biểu diễn trên cùng một instant. Không dùng chuỗi ngày giờ thiếu timezone như `2020-01-01 00:00:00`, vì cách hiểu có thể phụ thuộc timezone mặc định của máy.

Các yếu tố cần kiểm soát:

- Timezone của JVM và hệ điều hành.
- Locale khi format ngày giờ.
- Định dạng ISO-8601 thống nhất.
- Độ chính xác của timestamp được tạo từ source metadata.
- Cách từng plugin chuyển timestamp sang metadata ZIP.

`jar --list --verbose` hiển thị thời gian theo cách formatter của môi trường đang chạy; khi đối chiếu giữa các máy, cần xem xét timezone hiển thị và giá trị timestamp đầu vào.

## 13. Timestamp của .class và incremental compilation

`javac` không nhúng thời gian compile hiện tại vào bytecode `.class` như một trường timestamp riêng. Với cùng source, compiler version và options, việc chỉ thay đổi filesystem mtime của file `.java` không nhất thiết làm nội dung class file thay đổi.

Tuy nhiên, mtime vẫn được build tool dùng để quyết định có cần compile lại hay không. Vì vậy:

- Không chỉnh mtime source file để ép build system bỏ qua compile.
- Không dùng class output cũ làm bằng chứng cho build mới.
- Khi kiểm tra reproducibility, có thể clean rồi build lại từ cùng source.
- So sánh bytecode bằng hash sau khi dùng cùng JDK và compiler options.
- Giữ compiler JDK và `--release` nhất quán.

Ví dụ:

~~~bash
javac --release 17 -g -d build/classes src/main/java/com/example/Main.java
~~~

Thay đổi mtime của source có thể khiến compiler chạy lại, nhưng nếu nội dung source và compiler input không đổi thì class file vẫn có thể giống nhau.

## 14. Kiểm tra timestamp trong JAR

Liệt kê entry và timestamp:

~~~bash
jar --list --verbose --file build/app.jar
~~~

Để xem manifest:

~~~bash
jar --extract --file build/app.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
~~~

Trên PowerShell:

~~~powershell
jar --extract --file build/app.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
~~~

Kiểm tra hash:

~~~bash
sha256sum build/app.jar
~~~

Trên PowerShell:

~~~powershell
Get-FileHash build/app.jar -Algorithm SHA256
~~~

Quy trình so sánh:

1. Build artifact lần thứ nhất.
2. Lưu SHA-256.
3. Thay đổi mtime của source file mà không đổi nội dung source.
4. Clean và build lại bằng cùng toolchain/configuration.
5. So sánh SHA-256.
6. Nếu hash khác, kiểm tra timestamp entry, thứ tự entry, manifest, generated resource và nội dung từng file.

Hash giống nhau là bằng chứng mạnh cho thấy hai file có cùng bytes. Hash khác nhau cần được điều tra; đừng mặc định timestamp là nguyên nhân duy nhất.

## 15. Java 17 demo để kiểm tra artifact

Tạo file `src/main/java/com/example/Main.java`:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Stable timestamp build");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -g -d build/classes src/main/java/com/example/Main.java
~~~

Tạo JAR với timestamp cố định:

~~~bash
jar --create --date=2020-01-01T00:00:00Z --file build/app.jar -C build/classes .
~~~

Chạy:

~~~bash
java -cp build/app.jar com.example.Main
~~~

Stdout chính xác:

~~~text
Stable timestamp build
~~~

Tạo hai JAR ở hai lần chạy khác nhau, giữ nguyên nội dung class nhưng thay đổi filesystem mtime của class file. Nếu cả hai lần dùng cùng `--date`, cùng entry list và cùng thứ tự file, hash của hai JAR phải giống nhau.

Nếu bỏ `--date`, timestamp entry có thể lấy từ mtime của file đầu vào và làm hash thay đổi.

## 16. Lab Maven: build hai lần với cùng SOURCE_DATE_EPOCH

Ví dụ `pom.xml` tối giản:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>stable-timestamp-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <project.build.outputTimestamp>${env.SOURCE_DATE_EPOCH}</project.build.outputTimestamp>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <encoding>UTF-8</encoding>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy trên PowerShell:

~~~powershell
$env:SOURCE_DATE_EPOCH = "1577836800"
mvn -B clean package

Get-FileHash target/stable-timestamp-demo-1.0.0.jar -Algorithm SHA256

# Thay đổi mtime của source nhưng giữ nguyên nội dung.
(Get-Item src/main/java/com/example/Main.java).LastWriteTimeUtc =
    [DateTime]::UtcNow.AddDays(-2)

mvn -B clean package
Get-FileHash target/stable-timestamp-demo-1.0.0.jar -Algorithm SHA256
~~~

Hai hash phải giống nhau nếu các plugin và nội dung build khác cũng reproducible. Kiểm tra entry timestamp:

~~~bash
jar --list --verbose --file target/stable-timestamp-demo-1.0.0.jar
~~~

Trong thử nghiệm JDK 24.0.2, Maven 3.9.12 và Maven JAR Plugin 3.4.2, `SOURCE_DATE_EPOCH=1577836800` tạo entry timestamp tương ứng với `2020-01-01T00:00:00Z`. Hai lần `clean package` sau khi thay đổi source mtime tạo JAR có SHA-256 giống nhau.

## 17. Lab Gradle: chuẩn hóa timestamp và thứ tự entry

Ví dụ `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(24)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
    options.encoding = 'UTF-8'
}

tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
~~~

Build:

~~~bash
gradle clean jar
~~~

Kiểm tra hash:

~~~bash
sha256sum build/libs/gradle-1.0.0.jar
~~~

Thay đổi mtime source rồi build lại:

~~~bash
gradle clean jar
sha256sum build/libs/gradle-1.0.0.jar
~~~

Hai hash phải giống nhau nếu nội dung source và toàn bộ input khác không đổi.

Trong thử nghiệm Gradle 9.2.1, archive entry được chuẩn hóa về timestamp ZIP-compatible `1980-02-01`; hai lần `clean jar` sau khi thay đổi source mtime tạo JAR có SHA-256 giống nhau. Gradle vẫn ghi thời gian chạy task trong console log; các dòng log đó không được đưa vào JAR.

## 18. Vì sao hash vẫn có thể khác dù timestamp đã ổn định?

Timestamp chỉ là một phần của metadata. Một số nguyên nhân khác:

- File được thêm vào archive theo thứ tự khác nhau.
- Manifest có `Build-Time`, `Created-By` hoặc metadata động.
- Plugin tạo generated source/resource có thời gian hiện tại.
- Compiler JDK hoặc vendor khác nhau.
- Dependency được resolve thành phiên bản khác.
- Resource filtering ghi đường dẫn tuyệt đối hoặc username.
- Newline, encoding, locale hoặc timezone khác nhau.
- Một plugin archive không hỗ trợ reproducible output.
- Nội dung build-info chứa commit metadata hoặc build number thay đổi.
- Archive có file permission hoặc metadata khác nhau giữa hệ điều hành.

Nếu hash khác, so sánh archive đã giải nén hoặc dùng công cụ như `diffoscope` để tìm entry khác. Xác định plugin tạo entry đó rồi cấu hình reproducible output cho chính plugin.

Không sửa timestamp bằng cách `touch` file JAR cuối cùng. Việc này chỉ thay mtime của file trên filesystem, không sửa timestamp entry bên trong archive và không làm byte của JAR trở nên reproducible.

## 19. Lỗi thường gặp khi ổn định timestamp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai JAR khác hash dù class giống nhau | ZIP entry timestamp khác. | Dùng `jar --date`, Maven `project.build.outputTimestamp` hoặc Gradle `preserveFileTimestamps=false`. |
| Đã export `SOURCE_DATE_EPOCH` nhưng JAR CLI vẫn dùng giờ hiện tại | `jar` không tự đọc biến này. | Chuyển epoch thành ISO UTC và truyền `--date`. |
| Maven vẫn tạo JAR khác nhau | Plugin không hỗ trợ output timestamp hoặc manifest/resource có thời gian động. | Pin plugin hỗ trợ reproducible build và kiểm tra generated files. |
| Gradle JAR thay đổi theo thứ tự file | Archive task chưa bật reproducible order. | Đặt `reproducibleFileOrder=true`. |
| Timestamp hiển thị lệch giờ | Timezone đầu vào hoặc timezone hiển thị khác nhau. | Dùng UTC `Z` và thống nhất timezone khi so sánh. |
| Timestamp trong manifest thay đổi | Dùng `${maven.build.timestamp}` hoặc `new Date()`. | Dùng mốc từ source revision hoặc bỏ field thời gian. |
| Hash khác dù entry time giống nhau | Nội dung, thứ tự entry, permissions hoặc manifest khác. | So sánh từng entry và kiểm tra plugin tạo archive. |
| CI không có SOURCE_DATE_EPOCH | Pipeline không truyền commit metadata. | Tạo biến từ Git commit hoặc truyền epoch từ release process. |
| Build local pass nhưng CI khác | JDK/toolchain, plugin hoặc dependency khác. | Pin toolchain, plugin version và dependency. |
| Archive có entry trước năm 1980 | Timestamp nằm ngoài phạm vi ZIP-compatible của một số archive task. | Chọn mốc timestamp hợp lệ, ổn định và dùng chung. |

## 20. Quy trình chuẩn hóa timestamp trong CI

1. Chọn mốc thời gian ổn định cho source revision, thường là Git committer timestamp.
2. Export `SOURCE_DATE_EPOCH` dưới dạng Unix seconds UTC.
3. Xác định archive tool nào tạo JAR/ZIP/TAR trong build.
4. Với `jar`, chuyển epoch sang ISO UTC và truyền `--date`.
5. Với Maven, cấu hình `project.build.outputTimestamp` và dùng plugin có hỗ trợ reproducible output.
6. Với Gradle, đặt `preserveFileTimestamps=false` và `reproducibleFileOrder=true`.
7. Loại bỏ thời gian build động khỏi manifest và generated resource.
8. Giữ compiler, dependency, locale, encoding và file order ổn định.
9. Build sạch hai lần từ cùng source revision.
10. So sánh SHA-256 của artifact.
11. Nếu hash khác, kiểm tra timestamp entry và so sánh nội dung từng file.
12. Lưu hash, toolchain version và source revision vào build report.

Có thể kiểm tra hash trên Linux/macOS bằng `sha256sum`, hoặc PowerShell bằng `Get-FileHash -Algorithm SHA256`. So sánh file artifact, không dùng mtime của file trên filesystem làm bằng chứng duy nhất.

## 21. Tài liệu tham khảo

- [The jar Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Configuring for Reproducible Builds — Maven](https://maven.apache.org/guides/mini/guide-reproducible-builds.html)
- [Maven JAR Plugin — jar:jar](https://maven.apache.org/plugins/maven-jar-plugin/jar-mojo.html)
- [Gradle AbstractArchiveTask](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.bundling.AbstractArchiveTask.html)
- [Gradle Jar Task](https://docs.gradle.org/current/dsl/org.gradle.jvm.tasks.Jar.html)
- [SOURCE_DATE_EPOCH specification](https://reproducible-builds.org/docs/source-date-epoch/)

Ổn định timestamp giúp loại bỏ một nguồn khác biệt phổ biến giữa các lần build Java. Dùng `SOURCE_DATE_EPOCH` làm nguồn thời gian cố định, truyền `--date` cho `jar`, cấu hình `project.build.outputTimestamp` trong Maven và tắt việc giữ file timestamp trong Gradle. Sau đó so sánh SHA-256 để xác nhận artifact thực sự giống nhau.
