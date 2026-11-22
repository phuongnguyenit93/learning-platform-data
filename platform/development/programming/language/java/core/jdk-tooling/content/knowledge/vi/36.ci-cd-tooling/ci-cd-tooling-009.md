# Dùng jdeprscan trong CI để phát hiện Java API deprecated

**jdeprscan** là công cụ đi kèm JDK để quét bytecode và tìm những lần sử dụng Java SE API đã được đánh dấu deprecated. Trong CI, có thể chạy nó sau khi compile/package để phát hiện API cũ trong class directory hoặc JAR trước khi phát hành.

Điểm quan trọng khi biến nó thành quality gate: **jdeprscan có thể tìm thấy deprecated API nhưng vẫn trả exit code 0**. Vì vậy, chỉ chạy lệnh và dựa vào exit code sẽ không làm build thất bại khi có cảnh báo. Pipeline cần kiểm tra output, phát hiện các dòng báo usage và tự trả exit code khác 0 theo policy của dự án.

Bài này hướng dẫn:

- Hiểu phạm vi và giới hạn của jdeprscan.
- Chọn đúng JDK và Java SE release để quét.
- Quét class file, directory và JAR.
- Phân biệt deprecated API thông thường với API deprecated for removal.
- Viết CI gate cho Bash và PowerShell.
- Tích hợp sau Maven hoặc Gradle build.
- Quản lý dependency, multi-module project và kết quả scan.

## 1. jdeprscan làm gì?

jdeprscan đọc bytecode đã biên dịch và tìm tham chiếu tới các API Java SE được đánh dấu deprecated trong danh sách của Java release được chọn.

Ví dụ, source code có thể gọi:

- java.util.Date.getYear().
- java.net.URL(String).
- Constructor của java.lang.Integer.
- java.lang.Thread.stop().

Nếu API đã deprecated trong release được chọn, scanner sẽ báo class nào đang tham chiếu tới API đó.

Một dòng kết quả có dạng:

~~~text
class com/example/DeprecatedApiDemo uses deprecated method java/util/Date::getYear()I
~~~

Nếu API được đánh dấu deprecated for removal, kết quả có thêm:

~~~text
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
~~~

Điều này giúp nhóm phát triển tìm được:

- Code nội bộ còn gọi API cũ.
- Thư viện hoặc module cần nâng cấp.
- API đang tiến gần tới việc bị loại bỏ.
- Những tham chiếu cần xử lý trước khi nâng cấp JDK.

### jdeprscan không thay thế các công cụ khác

| Công cụ | Vai trò |
|---|---|
| javac -Xlint:deprecation | Cảnh báo khi biên dịch source code |
| jdeprscan | Quét bytecode đã biên dịch để tìm Java SE API deprecated |
| jdeps --jdk-internals | Tìm tham chiếu tới JDK internal API |
| Unit/integration tests | Kiểm tra hành vi của ứng dụng |
| Dependency scanner | Kiểm tra phiên bản và lỗ hổng của dependency |

jdeprscan tập trung vào deprecated API của Java SE. Nó không phải công cụ kiểm tra mọi annotation @Deprecated của mọi thư viện bên thứ ba, không phải vulnerability scanner và không thay thế test.

Nếu mục tiêu là tìm JDK internal API, hãy dùng thêm jdeps --jdk-internals. Một API không deprecated vẫn có thể là internal API không được hỗ trợ ổn định.

## 2. Vì sao nên chạy trong CI?

Deprecated API có thể vẫn hoạt động trong JDK hiện tại, nhưng có thể bị loại bỏ trong release tương lai. Nếu dự án để usage tích tụ lâu dài, việc nâng cấp JDK có thể trở nên khó khăn vì không biết module nào đang phụ thuộc vào API cũ.

Đặt scan trong CI mang lại các lợi ích:

- Phát hiện usage mới ngay trong pull request.
- Giữ số lượng deprecated API không tăng theo thời gian.
- Ưu tiên xử lý API được đánh dấu for removal.
- Theo dõi module hoặc dependency gây ra cảnh báo.
- Tạo bằng chứng kiểm tra tương thích khi nâng cấp JDK.

Nên chạy scan sau khi compile và package, vì jdeprscan cần bytecode. Có thể quét thư mục class output trước khi đóng gói hoặc quét JAR cuối cùng trước khi publish.

Một pipeline cơ bản:

~~~text
Checkout
   |
   v
Set up JDK
   |
   v
Compile and test
   |
   v
Package JAR
   |
   v
Run jdeprscan
   |
   +---- No deprecated usage ----> Continue publish
   |
   +---- Deprecated usage ------> Fail quality gate
~~~

## 3. Cài đặt và xác nhận đúng JDK

jdeprscan được phân phối cùng JDK. CI agent cần cài JDK có chứa công cụ này; runtime image rút gọn có thể không có các developer tools.

Kiểm tra trên Linux/macOS:

~~~bash
java -version
javac -version
jdeprscan --version
command -v jdeprscan
~~~

Trên Windows PowerShell:

~~~powershell
java -version
javac -version
jdeprscan --version
Get-Command jdeprscan
~~~

Có thể dùng đường dẫn trực tiếp từ JAVA_HOME:

Linux/macOS:

~~~bash
"$JAVA_HOME/bin/jdeprscan" --version
~~~

Windows:

~~~powershell
& "$env:JAVA_HOME\bin\jdeprscan.exe" --version
~~~

Khi chạy trong CI, hãy bảo đảm java, javac và jdeprscan đến từ JDK dự kiến. Nếu PATH trỏ tới một JDK khác, kết quả scan có thể dùng danh sách deprecated API không đúng với mục tiêu nâng cấp.

JDK 24.0.2 được dùng để kiểm thử bài này. Công cụ trên môi trường đó hỗ trợ các giá trị --release từ 8 đến 24. Danh sách release có thể khác theo phiên bản JDK; kiểm tra jdeprscan --help trên đúng CI image.

## 4. Cú pháp và các tùy chọn chính

Cú pháp tổng quát:

~~~bash
jdeprscan [options] {dir|jar|class} ...
~~~

Các loại input được hỗ trợ:

- Directory là root của package hierarchy.
- JAR file.
- Class file.
- Tên class đầy đủ, ví dụ java.lang.Thread$State.

Các tùy chọn thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| --release N | Chọn Java SE release cung cấp danh sách deprecated API |
| --for-removal | Chỉ quét API đã deprecated for removal |
| --class-path PATH | Đường dẫn hỗ trợ resolve các dependent class |
| --list | Liệt kê deprecated API, không quét input |
| --verbose | In thêm thông tin khi xử lý |
| --version | In phiên bản rút gọn |
| --full-version | In phiên bản đầy đủ |
| --help | In hướng dẫn |

Xem trợ giúp:

~~~bash
jdeprscan --help
~~~

Xem danh sách API deprecated:

~~~bash
jdeprscan --list
~~~

Chỉ liệt kê API for removal:

~~~bash
jdeprscan --list --for-removal
~~~

--list chỉ in danh sách API, không phải lệnh scan artifact. Không truyền directory, JAR hoặc class khi dùng --list.

## 5. Chọn đúng --release

--release chọn bộ dữ liệu deprecated API của Java SE release cần kiểm tra. Nó không thay đổi bytecode và cũng không thay thế tùy chọn --release của javac.

Ví dụ:

~~~bash
jdeprscan --release 17 build/libs/app.jar
~~~

Lệnh trên hỏi: artifact này có tham chiếu tới API được đánh dấu deprecated trong Java SE 17 hay không?

Nếu đang chuẩn bị nâng cấp lên Java 24:

~~~bash
jdeprscan --release 24 build/libs/app.jar
~~~

Điều này có thể phát hiện API chỉ được deprecated trong các release sau Java 17.

Trong JDK 24.0.2, URL(String) đã deprecated từ Java 20. Khi quét cùng một class:

- --release 17 không báo URL(String).
- --release 24 báo URL(String).

Vì vậy, hãy chọn release theo mục tiêu:

| Mục tiêu | Cách chọn |
|---|---|
| Giữ compatibility với Java 17 | --release 17 |
| Chuẩn bị chuyển runtime lên Java 21 | --release 21 |
| Chuẩn bị chuyển runtime lên Java 24 | --release 24 |
| Theo dõi nhiều target runtime | Chạy scan riêng cho từng release được hỗ trợ |

Nếu tool JDK đang cài không hỗ trợ release mục tiêu, hãy nâng cấp JDK dùng trong CI. Ví dụ, JDK 24 không thể cung cấp bộ dữ liệu cho một release tương lai chưa được hỗ trợ.

## 6. Phân biệt deprecated và deprecated for removal

Không phải mọi API deprecated đều có cùng mức độ khẩn cấp.

**Deprecated thông thường:** API không còn được khuyến nghị; developer nên tìm API thay thế nhưng chưa có tuyên bố rằng API sẽ bị loại bỏ.

**Deprecated for removal:** API được đánh dấu rõ ràng có ý định loại bỏ trong một release tương lai. Đây thường là nhóm cần ưu tiên xử lý.

Quét tất cả deprecated API:

~~~bash
jdeprscan --release 24 build/libs/app.jar
~~~

Chỉ quét API for removal:

~~~bash
jdeprscan --release 24 --for-removal build/libs/app.jar
~~~

Dòng có forRemoval=true cho biết API thuộc nhóm này.

Một policy thực tế có thể là:

- Báo cáo tất cả deprecated API để nhóm lên kế hoạch xử lý.
- Làm quality gate nghiêm ngặt với API for removal.
- Sau khi giảm legacy usage, chuyển dần sang gate cho toàn bộ deprecated API.

--for-removal là bộ lọc. Nó không có nghĩa các API deprecated khác an toàn hoặc sẽ tồn tại mãi mãi.

## 7. Quét class file, directory và JAR

### Quét một class file

~~~bash
jdeprscan --release 24 build/classes/java/main/com/example/LegacyClient.class
~~~

Tên class trong bytecode vẫn theo package hierarchy. Không truyền source file .java vì jdeprscan đọc bytecode.

### Quét một directory

~~~bash
jdeprscan --release 24 build/classes/java/main
~~~

Directory phải là root của package hierarchy. Scanner đi qua các class trong cây thư mục đó.

### Quét một JAR

~~~bash
jdeprscan --release 24 build/libs/application.jar
~~~

Đây là lựa chọn phù hợp cho pipeline kiểm tra artifact sau package.

### Quét nhiều input

~~~bash
jdeprscan --release 24 module-a/build/classes/java/main module-b/build/classes/java/main build/libs/application.jar
~~~

Có thể truyền nhiều directory, JAR hoặc class trong cùng một lần gọi. Trong multi-module project, cần bảo đảm tất cả output của module cần kiểm tra đều được đưa vào danh sách.

### Quét class name

~~~bash
jdeprscan --release 24 java.lang.Thread$State
~~~

Tên class phải fully qualified. Với nested class, dùng dấu $ làm separator.

## 8. Dùng --class-path để resolve dependency

Một số class cần dependency để scanner resolve tham chiếu. Dùng --class-path để cung cấp đường dẫn tìm dependent class:

Linux/macOS:

~~~bash
jdeprscan --release 24 --class-path "build/classes:lib/*" build/libs/application.jar
~~~

Windows:

~~~powershell
jdeprscan --release 24 --class-path "build\classes;lib\*" build\libs\application.jar
~~~

Dấu phân cách class path phụ thuộc hệ điều hành: dấu hai chấm trên Unix-like và dấu chấm phẩy trên Windows.

**Class path dùng để resolve dependency; nó không tự động biến mọi dependency thành input được quét.** Nếu muốn kiểm tra deprecated usage bên trong thư viện, hãy truyền chính JAR của thư viện đó làm input riêng.

Thử nghiệm trên JDK 24.0.2:

- app.jar gọi một method trong legacy-lib.jar.
- Quét app.jar với legacy-lib.jar trên --class-path không báo deprecated usage bên trong thư viện.
- Quét legacy-lib.jar như một input riêng phát hiện Date.getYear().

Vì vậy, pipeline có thể cần quét cả artifact của dự án và các dependency mà nhóm muốn kiểm soát. Không phải lúc nào cũng cần quét toàn bộ dependency tree; hãy xác định phạm vi theo ownership, policy và khả năng resolve class.

## 9. Ví dụ Java 17+: tạo artifact có deprecated API

Ví dụ này dùng ba API:

- Date.getYear(): deprecated từ lâu.
- URL(String): deprecated từ Java 20.
- Integer(int): deprecated for removal.

### DeprecatedApiDemo.java

~~~java
package com.example;

import java.net.URL;
import java.util.Date;

public final class DeprecatedApiDemo {
    public static void main(String[] args) throws Exception {
        Date epoch = new Date(0L);
        URL url = new URL("https://example.com/");
        Integer boxed = new Integer(42);

        System.out.println("legacy year=" + epoch.getYear());
        System.out.println("host=" + url.getHost());
        System.out.println("boxed=" + boxed);
    }
}
~~~

### CleanApiDemo.java

~~~java
package com.example;

import java.time.Instant;

public final class CleanApiDemo {
    public static void main(String[] args) {
        System.out.println(Instant.ofEpochSecond(0).getEpochSecond());
    }
}
~~~

Biên dịch:

~~~bash
mkdir -p build/classes

javac --release 17 -Xlint:deprecation -d build/classes src/com/example/DeprecatedApiDemo.java src/com/example/CleanApiDemo.java
~~~

javac phát cảnh báo cho những API deprecated trong compile-time API view đang được chọn. Có thể dùng thêm lint và compiler policy của dự án để cảnh báo sớm ngay lúc compile.

Chạy chương trình:

~~~bash
java -cp build/classes com.example.DeprecatedApiDemo
~~~

Stdout chính xác:

~~~text
legacy year=70
host=example.com
boxed=42
~~~

Ví dụ dùng Date với epoch 0 để kết quả year ổn định. URL chỉ được tạo và đọc host; không có request mạng nào được gửi.

## 10. Quét và đọc kết quả của ví dụ

### Scan theo Java 17

~~~bash
jdeprscan --release 17 build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
class com/example/DeprecatedApiDemo uses deprecated method java/util/Date::getYear()I
~~~

URL(String) chưa deprecated trong Java 17 nên không xuất hiện.

### Scan theo Java 24

~~~bash
jdeprscan --release 24 build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/example/DeprecatedApiDemo uses deprecated method java/net/URL::<init>(Ljava/lang/String;)V
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
class com/example/DeprecatedApiDemo uses deprecated method java/util/Date::getYear()I
~~~

URL(String) xuất hiện vì API này đã deprecated trong Java 24.

### Chỉ quét API for removal

~~~bash
jdeprscan --release 24 --for-removal build/classes
~~~

Output:

~~~text
Directory build/classes:
class com/example/DeprecatedApiDemo uses deprecated method java/lang/Integer::<init>(I)V (forRemoval=true)
~~~

### Quét class sạch

~~~bash
jdeprscan --release 24 build/classes/com/example/CleanApiDemo.class
~~~

Lệnh không in dòng deprecated usage nào. Đây là kết quả mong muốn cho class sạch.

### Đóng gói và quét JAR

~~~bash
jar --create --file build/libs/demo.jar -C build/classes .
jdeprscan --release 24 build/libs/demo.jar
~~~

Output của JAR có cùng các deprecated reference trong DeprecatedApiDemo. Scanner không cần chạy ứng dụng để tìm các reference này.

Các output trên đã được kiểm tra trên JDK 24.0.2. Đường dẫn trong output thực tế sẽ theo vị trí artifact trên CI agent.

## 11. Quan trọng: jdeprscan không tự làm build thất bại

Khi quét artifact có deprecated API, jdeprscan 24.0.2 in các dòng uses deprecated nhưng vẫn trả exit code 0.

Đã kiểm tra:

| Input | Deprecated finding | Exit code của jdeprscan |
|---|---:|---:|
| DeprecatedApiDemo.class | Có | 0 |
| demo.jar chứa class deprecated | Có | 0 |
| CleanApiDemo.class | Không | 0 |

Điều này có nghĩa pipeline sau đây chưa đủ:

~~~bash
jdeprscan --release 24 build/libs/app.jar
~~~

CI sẽ tiếp tục vì command trả về 0 dù output có finding. Để tạo quality gate, cần kiểm tra output và tự đặt exit code khác 0 khi phát hiện deprecated usage.

Một gate tốt nên xử lý ba trường hợp:

1. Scanner chạy thành công và không có finding: pass.
2. Scanner chạy thành công nhưng có deprecated usage: fail theo policy.
3. Scanner không chạy được hoặc có diagnostic không resolve được: fail để tránh kết luận sai rằng artifact sạch.

## 12. Tạo CI gate bằng Bash

Tạo file ci/check-jdeprscan.sh:

~~~bash
#!/usr/bin/env bash

set -u

artifact="$1"
release=17
log=jdeprscan.log

if [ "$#" -ge 2 ]; then
    release="$2"
fi

if [ "$#" -ge 3 ]; then
    log="$3"
fi

jdeprscan --release "$release" "$artifact" > "$log" 2>&1
tool_status=$?

cat "$log"

if [ "$tool_status" -ne 0 ]; then
    echo "jdeprscan execution failed with exit code $tool_status"
    exit "$tool_status"
fi

if grep -Eq ' uses deprecated |^(Warning|Error):' "$log"; then
    echo "Deprecated API usage or unresolved scan diagnostic found in $artifact"
    exit 1
fi

echo "No deprecated API usage found in $artifact"
exit 0
~~~

Cấp quyền chạy trên Linux/macOS:

~~~bash
chmod +x ci/check-jdeprscan.sh
~~~

Chạy sau Maven:

~~~bash
mvn -B package
./ci/check-jdeprscan.sh target/application.jar 17
~~~

Chạy sau Gradle:

~~~bash
./gradlew clean jar
./ci/check-jdeprscan.sh build/libs/application.jar 17
~~~

Tham số thứ hai là Java SE release cần kiểm tra. Nếu muốn ghi log vào vị trí khác, truyền tham số thứ ba.

Script lưu output để có thể upload log làm CI artifact. Nó kiểm tra cả exit code của công cụ và các dòng báo deprecated usage hoặc diagnostic.

Nếu muốn chỉ chặn API for removal, thay lệnh scan trong script bằng:

~~~bash
jdeprscan --release "$release" --for-removal "$artifact" > "$log" 2>&1
~~~

Khi áp dụng policy này, API deprecated thông thường vẫn có thể được báo cáo ở một job khác mà không làm fail build.

## 13. Tạo CI gate bằng PowerShell

Với Windows runner, có thể dùng script sau:

~~~powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,

    [ValidateRange(8, 24)]
    [int]$Release = 17,

    [switch]$ForRemoval
)

$scanArgs = @('--release', $Release.ToString())

if ($ForRemoval) {
    $scanArgs += '--for-removal'
}

$scanArgs += $Artifact

$output = @(& jdeprscan @scanArgs 2>&1)
$toolExit = $LASTEXITCODE

$output | Tee-Object -FilePath 'jdeprscan.log'

if ($toolExit -ne 0) {
    Write-Output "jdeprscan failed with exit code $toolExit"
    exit $toolExit
}

$findings = @(
    $output | Where-Object {
        $_.ToString() -match ' uses deprecated '
    }
)

$diagnostics = @(
    $output | Where-Object {
        $_.ToString() -match '^(Warning|Error):'
    }
)

if ($findings.Count -gt 0 -or $diagnostics.Count -gt 0) {
    Write-Output "Deprecated API usage or unresolved scan diagnostic found."
    exit 1
}

Write-Output "No deprecated API usage found."
exit 0
~~~

Lưu thành ci/check-jdeprscan.ps1.

Chạy strict scan:

~~~powershell
.\ci\check-jdeprscan.ps1 -Artifact 'target\application.jar' -Release 17
~~~

Chỉ kiểm tra API for removal:

~~~powershell
.\ci\check-jdeprscan.ps1 -Artifact 'target\application.jar' -Release 24 -ForRemoval
~~~

Wrapper đã được thử với artifact deprecated và class sạch trên Windows PowerShell:

- Artifact deprecated: gate exit 1.
- Class sạch: gate exit 0.

Đây là exit code do wrapper tạo ra. Bản thân jdeprscan vẫn trả 0 trong cả hai trường hợp nếu scan chạy thành công.

## 14. Tích hợp vào pipeline CI

### GitHub Actions

Sau khi workflow đã thiết lập JDK phù hợp, có thể thêm các bước:

~~~yaml
- name: Build application
  run: mvn -B package

- name: Scan deprecated Java APIs
  run: bash ci/check-jdeprscan.sh target/application.jar 17

- name: Upload scan report
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: jdeprscan-report
    path: jdeprscan.log
    if-no-files-found: ignore
~~~

Nếu dùng PowerShell runner, gọi script .ps1 bằng pwsh thay cho Bash.

### GitLab CI

~~~yaml
stages:
  - build
  - quality

build:
  stage: build
  script:
    - mvn -B package
  artifacts:
    paths:
      - target/application.jar

deprecated-api-scan:
  stage: quality
  script:
    - bash ci/check-jdeprscan.sh target/application.jar 17
  artifacts:
    when: always
    paths:
      - jdeprscan.log
~~~

### Jenkins Pipeline

~~~groovy
pipeline {
    agent any

    stages {
        stage('Build') {
            steps {
                sh 'mvn -B package'
            }
        }

        stage('Deprecated API scan') {
            steps {
                sh 'bash ci/check-jdeprscan.sh target/application.jar 17'
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'jdeprscan.log',
                             allowEmptyArchive: true
        }
    }
}
~~~

Các ví dụ CI giả định JDK đã được cài và jdeprscan nằm trong PATH. Hãy dùng đúng shell cho runner. Nếu runner Windows, dùng PowerShell wrapper.

## 15. Multi-module project và dependency policy

Với Maven multi-module, mỗi module có thể tạo một hoặc nhiều JAR. Quét riêng từng artifact để biết module nào có deprecated usage.

Ví dụ:

~~~bash
./ci/check-jdeprscan.sh module-a/target/module-a.jar 17
./ci/check-jdeprscan.sh module-b/target/module-b.jar 17
./ci/check-jdeprscan.sh module-c/target/module-c.jar 17
~~~

Với Gradle:

~~~bash
./ci/check-jdeprscan.sh module-a/build/libs/module-a.jar 17
./ci/check-jdeprscan.sh module-b/build/libs/module-b.jar 17
~~~

Nếu dependency JAR được quản lý riêng, có thể quét chúng như input độc lập:

~~~bash
jdeprscan --release 24 module-a/target/module-a.jar module-b/target/module-b.jar lib/legacy-client.jar
~~~

Quy định rõ dependency nào thuộc phạm vi gate:

- Code do nhóm sở hữu: thường nên gate nghiêm ngặt.
- Thư viện bên thứ ba: có thể báo cáo riêng, pin version và theo dõi upstream.
- Thư viện không còn được duy trì: ghi nhận exception có thời hạn và kế hoạch thay thế.
- Dependency không resolve được: xử lý classpath trước khi coi scan là đáng tin cậy.

Không nên bỏ qua mọi finding chỉ vì nó đến từ dependency. Một thư viện deprecated có thể buộc dự án nâng cấp hoặc thay thế trước khi chuyển JDK.

## 16. Xử lý finding trong pull request

Khi CI phát hiện một API deprecated, nên xử lý theo thứ tự:

1. Xác định class và API được báo.
2. Mở source tương ứng hoặc tìm dependency sở hữu class.
3. Đọc Javadoc của API deprecated để hiểu lý do.
4. Tìm API thay thế được khuyến nghị.
5. Kiểm tra khác biệt hành vi, null handling, exception và hiệu năng.
6. Thay thế usage và thêm/điều chỉnh test.
7. Build lại và chạy jdeprscan.
8. Ghi nhận exception nếu chưa thể thay thế ngay.

Không thay thế API chỉ dựa trên tên tương tự. API mới có thể khác semantics hoặc có yêu cầu cấu hình khác.

Với API for removal, ưu tiên sửa sớm vì rủi ro nâng cấp cao hơn. Nếu chưa thể sửa, tạo ticket có owner, deadline và lý do kỹ thuật rõ ràng.

## 17. Giới hạn của jdeprscan

jdeprscan phân tích bytecode đã biên dịch và đối chiếu các tham chiếu tìm được với danh sách Java SE API deprecated của release được chọn. Nó là một bước kiểm tra có phạm vi rõ ràng, không phải bộ phân tích tương thích nhị phân hoặc công cụ chứng minh ứng dụng chạy được trên JDK mới.

Các giới hạn cần tính đến:

- **Chỉ quét input được truyền vào:** nếu không truyền dependency JAR, plugin JAR hoặc module artifact làm input, scanner không tự quét mọi tệp có thể xuất hiện trong runtime class path.
- **Không phân tích source code:** compile trước rồi quét class directory hoặc JAR. Mã nguồn chưa được biên dịch không nằm trong phạm vi.
- **Không thể suy ra lời gọi động:** tên class/method được tạo từ chuỗi, reflection, MethodHandle, service/plugin discovery hoặc bytecode sinh lúc runtime có thể không tạo ra constant-pool reference tĩnh mà scanner nhận diện được.
- **Không chứng minh mọi nhánh được thực thi:** finding là tham chiếu trong bytecode, không khẳng định nhánh đó sẽ chạy; ngược lại, scan sạch không chứng minh mọi code path an toàn.
- **Phụ thuộc release database:** --release chọn danh sách API deprecated theo Java SE release mục tiêu. Kết quả của release cũ không đại diện cho danh sách của release mới hơn. Dùng đúng release mà tổ chức đang nâng cấp tới.
- **Không thay thế kiểm tra thư viện bên thứ ba:** deprecated annotation của API ngoài Java SE không nhất thiết thuộc dữ liệu mà jdeprscan sử dụng.
- **Không phát hiện mọi thay đổi tương thích:** thay đổi hành vi, cấu hình mặc định, module access, internal API, native library, serialization, TLS hoặc security policy có thể gây lỗi dù không có deprecated reference.
- **Không tự đánh giá mức độ rủi ro:** một reference có thể nằm trong code ít dùng hoặc trong đường chạy quan trọng. Cần gắn finding với owner, call path, mức ảnh hưởng và kế hoạch thay thế.

Một kết quả sạch chỉ có nghĩa là không tìm thấy reference deprecated thuộc phạm vi input và release đã quét. Kết hợp jdeprscan với jdeps để xem dependency/module, compiler warning, integration test trên JDK đích và kiểm thử migration. Với API được gọi qua reflection hoặc plugin, bổ sung test runtime và kiểm tra cấu hình nạp module tương ứng.

## 18. Lỗi thường gặp

### Không tìm thấy lệnh jdeprscan

Kiểm tra JDK đã cài, JAVA_HOME và PATH. Một runtime image tối giản có thể không chứa công cụ.

### Release không được hỗ trợ

Chạy jdeprscan --help và kiểm tra danh sách release. Dùng JDK mới hơn nếu cần quét một Java SE release mới hơn.

### Scan source file .java

jdeprscan đọc bytecode. Hãy compile trước, rồi truyền class directory hoặc JAR.

### Không có output dù source có deprecated annotation

Kiểm tra bytecode có thật sự chứa reference không. Code không được compile vào artifact hoặc code path chỉ được tạo runtime sẽ không xuất hiện trong scan.

### --release 17 không báo API deprecated từ Java 20

Đây là hành vi đúng. --release chọn bộ dữ liệu của Java SE 17. Dùng --release 24 nếu đang chuẩn bị nâng cấp lên Java 24.

### --for-removal không báo tất cả deprecated API

Đây là chế độ lọc chỉ giữ API được đánh dấu for removal. Bỏ tùy chọn nếu muốn xem toàn bộ deprecated API.

### CI không fail dù có finding

jdeprscan có thể trả exit code 0 khi đã tìm thấy deprecated usage. Hãy dùng wrapper kiểm tra output và tạo exit code khác 0 theo policy.

### Quét application JAR nhưng bỏ sót dependency

--class-path giúp resolve dependent class; nó không tự quét mọi JAR trong class path. Truyền dependency JAR làm input riêng nếu muốn kiểm tra chúng.

### Scan báo lỗi resolve class

Cung cấp dependency cần thiết qua --class-path. Kiểm tra path separator của hệ điều hành và bảo đảm file dependency có mặt trong CI workspace.

## 19. Checklist cho CI quality gate

- [ ] Runner cài JDK có jdeprscan.
- [ ] java, javac và jdeprscan đến từ cùng JDK dự kiến.
- [ ] Chọn đúng Java SE release cho mục tiêu kiểm tra.
- [ ] Build artifact trước khi scan.
- [ ] Quét toàn bộ class directory hoặc JAR cần kiểm tra.
- [ ] Quét dependency JAR riêng nếu policy yêu cầu.
- [ ] Dùng --for-removal nếu cần gate riêng cho API sắp bị loại bỏ.
- [ ] Lưu output của scanner làm CI artifact.
- [ ] Kiểm tra exit code của jdeprscan.
- [ ] Parse dòng uses deprecated để biến finding thành build failure.
- [ ] Fail khi scanner không chạy hoặc có diagnostic resolve class.
- [ ] Kiểm thử wrapper bằng một artifact có finding và một artifact sạch.
- [ ] Có owner và deadline cho exception.
- [ ] Chạy test sau khi thay API deprecated.
- [ ] Chạy lại scan sau khi nâng cấp JDK hoặc dependency.

## 20. Lệnh cần nhớ

~~~bash
# Check tool version and options
jdeprscan --version
jdeprscan --help

# List deprecated APIs
jdeprscan --list

# List APIs for removal
jdeprscan --list --for-removal

# Scan a compiled class directory
jdeprscan --release 17 build/classes

# Scan a class file
jdeprscan --release 24 build/classes/com/example/LegacyClient.class

# Scan a packaged JAR
jdeprscan --release 24 build/libs/application.jar

# Scan only APIs deprecated for removal
jdeprscan --release 24 --for-removal build/libs/application.jar

# Resolve dependencies while scanning the application artifact
jdeprscan --release 24 --class-path "build/classes:lib/*" build/libs/application.jar

# Scan project artifacts and a dependency separately
jdeprscan --release 24 build/libs/application.jar lib/legacy-client.jar

# Source-level deprecation warnings during compilation
javac --release 17 -Xlint:deprecation -d build/classes src/main/java/com/example/*.java

# CI gate
bash ci/check-jdeprscan.sh build/libs/application.jar 17
~~~

jdeprscan giúp biến việc phát hiện deprecated Java SE API thành một bước lặp lại được trong CI. Hãy quét bytecode sau khi build, chọn đúng --release, phân biệt API deprecated thông thường với API for removal và nhớ rằng finding không tự làm exit code khác 0. Một wrapper nhỏ kiểm tra output sẽ biến kết quả scan thành quality gate rõ ràng, có thể kiểm thử và lưu lại cùng artifact của pipeline.

## Tài liệu tham khảo

- [The jdeprscan Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeprscan.html)
- [The javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [The jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [Java Language Specification: Deprecated APIs](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/Deprecated.html)
