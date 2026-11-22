# So sánh checksum và truy tìm nguyên nhân artifact khác nhau

Trong một quy trình build có thể xuất hiện nhiều bản artifact được tạo từ cùng một mã nguồn: bản build trên máy lập trình viên, bản build trên CI, bản tải từ repository hoặc bản được chuyển sang môi trường triển khai. Nếu các file này có kích thước khác nhau hoặc không có cùng checksum, nhóm cần xác định chúng có thực sự khác nội dung hay chỉ khác metadata đóng gói.

**Checksum** là giá trị được tính từ nội dung của một file bằng thuật toán băm. So sánh checksum giúp xác định hai file có cùng byte hay không. Tuy nhiên, checksum chỉ cho biết sự khác biệt; nó không tự giải thích vì sao artifact khác nhau, ai đã tạo ra artifact hoặc artifact có đúng với mã nguồn dự kiến hay không.

Để truy tìm nguyên nhân, cần kết hợp checksum với thông tin nguồn, cấu hình build, dependency đã phân giải, môi trường thực thi và việc so sánh cấu trúc bên trong archive. Đây là một phần quan trọng của tính tái lập: cùng source, dependency và điều kiện build được kiểm soát nên tạo ra artifact có nội dung giống nhau.

## 1. Checksum là gì?

Checksum là một giá trị được tính từ dữ liệu đầu vào. Trong quy trình phát hành phần mềm, người ta thường dùng hàm băm mật mã như SHA-256 để tạo dấu vân tay cho artifact.

Ví dụ, file `order-service.jar` có thể tạo ra một chuỗi SHA-256 như:

```text
9a1d...e42c  order-service.jar
```

Chuỗi thực tế có độ dài 64 ký tự hex đối với SHA-256. Chỉ cần một byte trong file thay đổi, giá trị băm gần như chắc chắn sẽ khác.

Checksum có một số đặc điểm:

- Cùng một nội dung đầu vào và cùng thuật toán sẽ tạo ra cùng một giá trị băm.
- Giá trị băm có độ dài cố định, không phụ thuộc kích thước file.
- Không thể suy ngược thực tế nội dung ban đầu từ checksum như giải mã một bản mã.
- Một thay đổi nhỏ trong dữ liệu thường tạo ra giá trị băm rất khác.
- Với hàm băm mật mã mạnh như SHA-256, việc tìm hai nội dung khác nhau có cùng hash được xem là không khả thi về mặt thực tế trong các tình huống kiểm tra thông thường.

Checksum không phải mã hóa và cũng không phải chữ ký số. Nó là phép đo nhận diện nội dung theo byte.

## 2. Vì sao cần so sánh checksum của artifact?

Giả sử một ứng dụng được build trên CI rồi tải xuống máy triển khai. Nhóm muốn xác nhận file nhận được chính là file đã được tạo và phát hành.

```text
Source + Build configuration
             |
             v
        CI build
             |
             v
    order-service.jar -----> SHA-256: H1
             |
             v
        Artifact repository
             |
             v
    Downloaded JAR --------> SHA-256: H2
```

Nếu `H1` bằng `H2`, hai file có cùng nội dung byte theo thuật toán đã dùng. Điều đó giúp phát hiện file bị thay đổi hoặc hỏng trong quá trình lưu trữ, truyền tải hay sao chép.

Các trường hợp checksum hữu ích:

- So sánh artifact được tạo trên hai máy build.
- Xác nhận file tải từ repository giống file đã phát hành.
- Kiểm tra file không bị thay đổi sau khi chuyển giữa các môi trường.
- Phát hiện sự khác biệt giữa artifact của hai commit hoặc hai pipeline.
- Xác nhận cache hoặc bước copy đã cung cấp đúng file mong đợi.
- Ghi nhận định danh nội dung của artifact trong release manifest hoặc hồ sơ phát hành.

Checksum đặc biệt hữu ích khi cần chứng minh hai file giống nhau theo byte. Nếu hash khác nhau, bước tiếp theo là tìm xem byte nào khác và thay đổi bắt nguồn từ đâu.

## 3. Tính checksum bằng SHA-256

### 3.1. Linux

Trên nhiều hệ thống Linux có lệnh `sha256sum`:

```bash
# Tạo checksum
sha256sum order-service.jar

# Lưu checksum ra file bên cạnh artifact
sha256sum order-service.jar > order-service.jar.sha256

# Kiểm tra file theo checksum đã lưu
sha256sum -c order-service.jar.sha256
```

Nếu file không thay đổi, lệnh kiểm tra thường hiển thị `OK`. Nếu nội dung khác, kết quả sẽ báo `FAILED` hoặc trạng thái tương ứng.

### 3.2. macOS

Có thể dùng `shasum`:

```bash
shasum -a 256 order-service.jar
shasum -a 256 order-service.jar > order-service.jar.sha256
shasum -a 256 -c order-service.jar.sha256
```

Tham số `-a 256` chọn SHA-256. Không nên chỉ dựa vào tên file checksum; cần chắc chắn thuật toán được ghi rõ và giống nhau ở cả hai phía.

### 3.3. Windows PowerShell

PowerShell cung cấp `Get-FileHash`:

```powershell
Get-FileHash .\order-service.jar -Algorithm SHA256
```

Kết quả có các trường `Algorithm`, `Hash` và `Path`. Có thể tính cho hai artifact:

```powershell
$first = Get-FileHash .\build-a\order-service.jar -Algorithm SHA256
$second = Get-FileHash .\build-b\order-service.jar -Algorithm SHA256

$first.Hash -eq $second.Hash
```

Kết quả `True` cho biết hai file có cùng SHA-256; `False` cho biết chúng khác nhau theo byte.

### 3.4. Chọn thuật toán phù hợp

Đối với kiểm tra artifact hiện nay, ưu tiên SHA-256 hoặc thuật toán mạnh hơn được tổ chức hỗ trợ. Tránh dùng MD5 hoặc SHA-1 làm cơ chế xác thực bảo mật vì chúng không còn đáp ứng yêu cầu chống va chạm mật mã hiện đại.

CRC32 hoặc checksum đơn giản có thể phát hiện một số lỗi truyền tải ngẫu nhiên, nhưng không phù hợp để xác thực artifact trước nguy cơ bị cố ý thay đổi. Khi quy trình yêu cầu tính toàn vẹn có ý nghĩa bảo mật, hãy dùng hash mật mã và nguồn checksum đáng tin cậy.

## 4. Đọc kết quả so sánh checksum

Giả sử hai lần build tạo ra:

```text
Build A: 2f3a...9b10
Build B: 2f3a...9b10
```

Hai artifact giống nhau theo byte với SHA-256. Có thể tiếp tục dùng artifact đã xác minh theo quy trình phát hành.

Nếu kết quả là:

```text
Build A: 2f3a...9b10
Build B: 81ce...41af
```

Hai file khác nhau. Chưa thể kết luận mã nguồn khác, dependency khác hay có lỗi bảo mật. Hash chỉ cho biết nội dung byte không giống nhau.

Nên phân biệt ba trường hợp:

1. **Checksum giống nhau:** hai file giống nhau theo byte; đây là bằng chứng mạnh về tính đồng nhất nội dung.
2. **Checksum khác nhưng nội dung sau giải nén giống nhau:** có thể khác metadata archive như timestamp, thứ tự entry, cách nén hoặc phần metadata bên ngoài nội dung file.
3. **Checksum khác và có entry bên trong khác nhau:** cần xác định entry nào thay đổi, sau đó truy tìm nguồn sinh ra entry đó.

Một JAR là ZIP archive. Vì vậy, hai JAR có thể chứa cùng `.class` và resource nhưng khác byte do thời gian sửa file được ghi trong ZIP header hoặc thứ tự entry. Ngược lại, hai archive có cùng số lượng entry và kích thước gần nhau vẫn có thể chứa bytecode khác.

## 5. Checksum không chứng minh nguồn gốc artifact

Giả sử một máy chủ cung cấp hai file:

```text
order-service.jar
order-service.jar.sha256
```

Người nhận tải cả hai file từ cùng một nguồn rồi tính hash. Nếu giá trị khớp, file JAR phù hợp với checksum mà nguồn đó cung cấp. Nhưng nếu nguồn bị xâm nhập và kẻ tấn công thay cả JAR lẫn file checksum, phép kiểm tra vẫn có thể thành công.

Vì vậy, cần phân biệt:

| Cơ chế | Trả lời câu hỏi nào? | Giới hạn |
|---|---|---|
| Checksum/hash | File có cùng nội dung byte với giá trị hash tham chiếu không? | Không tự chứng minh ai tạo hoặc công bố hash |
| Chữ ký số | Nội dung có được ký bởi khóa tương ứng với chứng thư/khóa công khai đã tin cậy không? | Cần quản lý khóa và chuỗi tin cậy đúng |
| Build provenance/attestation | Artifact được tạo từ nguồn, quy trình và môi trường nào? | Cần hệ thống tạo và xác minh provenance đáng tin cậy |
| Reproducible build | Có thể tạo lại artifact tương đương byte từ đầu vào đã kiểm soát không? | Cần kiểm soát cả nguồn, dependency và yếu tố môi trường ảnh hưởng output |

Nếu cần xác nhận artifact do tổ chức phát hành, hãy lấy checksum từ một kênh được xác thực độc lập hoặc xác minh chữ ký số/attestation. Không coi một file `.sha256` đặt cạnh artifact trên cùng nguồn không tin cậy là bằng chứng đầy đủ về nguồn gốc.

## 6. Checksum và chữ ký số JAR

JAR hỗ trợ ký nội dung bằng công cụ `jarsigner`. Chữ ký số giúp xác minh nội dung được ký và danh tính khóa ký theo trust policy.

Kiểm tra chữ ký:

```bash
jarsigner -verify -verbose -certs order-service.jar
```

Để kết quả có ý nghĩa, cần xem thông tin signer, chứng thư, trạng thái tin cậy và cảnh báo của công cụ. Việc một archive có chữ ký hợp lệ về mặt toán học không tự động chứng minh signer là tổ chức mà người nhận tin cậy.

Chữ ký số và checksum có thể được dùng cùng nhau:

- SHA-256 giúp so sánh hoặc xác nhận nội dung file theo một giá trị đã biết.
- Chữ ký số giúp xác minh file được ký bởi khóa tương ứng.
- Provenance bổ sung thông tin về source commit, build workflow, builder và đầu vào.

Nếu chỉnh sửa entry trong một JAR đã ký, chữ ký của entry đó có thể không còn hợp lệ. Vì vậy, thứ tự phát hành thường là hoàn tất đóng gói, ký artifact, sau đó tính checksum của file cuối cùng để công bố. Khi điều tra tính tái lập, cũng có thể so sánh JAR trước bước ký để tách khác biệt do đóng gói khỏi khác biệt do quy trình ký.

## 7. So sánh artifact trước khi tìm nguyên nhân

Trước tiên, hãy chắc chắn đang so sánh đúng hai file:

- Cùng loại artifact, ví dụ cả hai đều là JAR ứng dụng, không so JAR với ZIP distribution.
- Cùng mô-đun và cùng classifier.
- Cùng phiên bản hoặc cùng source commit nếu mục tiêu là kiểm tra tính tái lập.
- Đã hoàn tất mọi bước đóng gói và ký theo cùng quy trình.
- Không vô tình so một file cũ trong cache với artifact mới.

Ghi lại tên, kích thước, thời gian tạo, đường dẫn và checksum của từng file. Thông tin này giúp tránh so nhầm artifact trước/sau khi ký hoặc nhầm output của một task với output phát hành.

Ví dụ Linux:

```bash
ls -l build-a/order-service.jar build-b/order-service.jar
sha256sum build-a/order-service.jar build-b/order-service.jar
```

Ví dụ PowerShell:

```powershell
Get-Item .\build-a\order-service.jar, .\build-b\order-service.jar |
    Select-Object FullName, Length, LastWriteTimeUtc

Get-FileHash .\build-a\order-service.jar, .\build-b\order-service.jar -Algorithm SHA256
```

Thời gian file trên filesystem không nhất thiết là timestamp được lưu bên trong archive. Không dùng `LastWriteTime` làm bằng chứng duy nhất về thời điểm nội dung được tạo.

## 8. Truy tìm khác biệt bên trong JAR/ZIP

### 8.1. Liệt kê entry

Dùng `jar tf` để xem danh sách entry:

```bash
jar tf build-a/order-service.jar > entries-a.txt
jar tf build-b/order-service.jar > entries-b.txt
diff -u entries-a.txt entries-b.txt
```

Nếu danh sách khác nhau, có entry được thêm, xóa hoặc đổi tên. Nếu danh sách giống nhau, nội dung byte của một hoặc nhiều entry vẫn có thể khác.

### 8.2. Xem kích thước và metadata archive

Với công cụ ZIP như `unzip` hoặc `zipinfo`:

```bash
unzip -lv build-a/order-service.jar
unzip -lv build-b/order-service.jar
```

Có thể quan sát kích thước nén, kích thước chưa nén và timestamp của entry. Nếu nội dung entry có vẻ giống nhau nhưng metadata khác, timestamp hoặc cách nén có thể là nguyên nhân khiến checksum toàn archive khác.

### 8.3. Giải nén và so sánh từng entry

Có thể giải nén hai JAR vào hai thư mục riêng:

```bash
mkdir extracted-a extracted-b
unzip -q build-a/order-service.jar -d extracted-a
unzip -q build-b/order-service.jar -d extracted-b
diff -ru extracted-a extracted-b
```

Nếu `diff` không báo khác biệt, các entry đã giải nén giống nhau theo nội dung mà công cụ so sánh. Archive vẫn có thể khác do ZIP metadata hoặc cách sắp xếp/nén entry.

Nếu có khác biệt, output sẽ chỉ ra file nào khác. Hãy bắt đầu với entry nhỏ và dễ hiểu như `META-INF/MANIFEST.MF`, properties, JSON hoặc resource được sinh tự động. Với `.class`, cần dùng công cụ phân tích bytecode hoặc so sánh output biên dịch để xác định thay đổi.

### 8.4. Dùng công cụ so sánh chuyên sâu

`diffoscope` là một công cụ có thể phân tích archive lồng nhau và chỉ ra khác biệt ở nhiều lớp như ZIP, JAR, manifest, file văn bản và binary. Khi có sẵn trong môi trường:

```bash
diffoscope build-a/order-service.jar build-b/order-service.jar
```

Nó có thể giúp rút ngắn quá trình tìm entry khác nhau. Output của công cụ vẫn cần được diễn giải cùng thông tin build; một khác biệt về timestamp có thể là nhiễu đóng gói, trong khi khác biệt trong class hoặc resource có thể phản ánh đầu vào thực sự khác.

## 9. Những nguyên nhân thường làm artifact khác nhau

### 9.1. Timestamp trong archive

JAR/ZIP có thể lưu thời gian sửa của entry. Nếu build A tạo file lúc 10:00 và build B tạo cùng file lúc 11:00, archive có thể khác byte dù nội dung `.class` không đổi.

Các timestamp có thể đến từ:

- Thời gian file nguồn hoặc file được copy.
- Thời gian tạo file sinh ra trong task.
- Timestamp được ghi vào ZIP entry.
- Build time được nhúng trong manifest hoặc resource.

Để có archive tái lập, cần chuẩn hóa timestamp thay vì dùng thời gian hiện tại của máy build.

### 9.2. Thứ tự entry trong archive

Nếu thứ tự file được duyệt từ filesystem hoặc collection không ổn định, hai lần đóng gói có thể ghi entry theo thứ tự khác nhau. Nội dung giải nén giống nhau nhưng byte của archive khác.

Build nên sắp xếp đầu vào archive theo thứ tự xác định. Gradle cung cấp tùy chọn archive reproducibility; các plugin Maven cũng cần cấu hình và phiên bản hỗ trợ output tái lập.

### 9.3. Dependency version hoặc artifact khác nhau

Hai máy có thể phân giải version khác nhau nếu build dùng version động như `1.+`, `latest.release`, metadata thay đổi hoặc repository không nhất quán. Dependency cùng tọa độ cũng có thể bị thay thế bởi artifact khác nếu repository nội bộ hoặc cache chứa nội dung không giống nhau.

Hãy kiểm tra:

- Version được khai báo và version thực tế được chọn.
- Dependency constraints, platform/BOM và resolution rules.
- Dependency lock state.
- Repository và mirror được sử dụng.
- Checksum verification metadata.
- Artifact classifier, variant và packaging.

### 9.4. Build tool, plugin hoặc JDK khác nhau

Gradle/Maven version khác nhau, plugin version khác nhau hoặc JDK/compiler khác nhau có thể tạo output khác. Compiler có thể thay đổi bytecode, metadata hoặc cách ghi debug information giữa các version.

Hãy so sánh Wrapper, Maven Wrapper, plugin version, JDK chạy build, Java toolchain, compiler options và release target. Chỉ ghi “đều dùng Java 21” chưa đủ; vendor hoặc bản cập nhật JDK có thể khác và plugin cũng có thể thay đổi.

### 9.5. Đường dẫn tuyệt đối và thông tin môi trường bị nhúng

Generated source, resource hoặc debug metadata có thể ghi đường dẫn workspace:

```text
C:\agent\_work\42\s\src\main\java\...
```

hoặc:

```text
/home/runner/work/order-service/order-service/src/main/java/...
```

Nếu hai máy dùng workspace khác nhau và compiler/task ghi đường dẫn đó vào output, `.class` hoặc generated file có thể khác nhau. Cần xem compiler debug options, source map, generated metadata và khả năng chuẩn hóa đường dẫn của toolchain.

### 9.6. Thời gian, timezone, locale và biến môi trường

Task sinh file có thể dùng `new Date()`, thời gian hiện tại, timezone, locale hoặc biến môi trường. Ví dụ, file `build-info.properties` chứa:

```properties
build.time=2026-11-13T08:00:00Z
build.host=runner-17
```

Hai lần build sẽ khác nhau dù source giống nhau. Nếu thông tin build time/host cần thiết cho vận hành, cần quyết định có chấp nhận artifact không tái lập hay không, hoặc chuyển thông tin đó vào provenance/attestation bên ngoài artifact.

Một số công cụ hỗ trợ biến môi trường `SOURCE_DATE_EPOCH` để dùng timestamp chuẩn hóa, nhưng không phải mọi Gradle plugin, Maven plugin hoặc task tự viết đều tự động tuân theo. Chỉ dựa vào biến này khi công cụ cụ thể có hỗ trợ và đã xác nhận hành vi.

### 9.7. Generated files và thứ tự xử lý

Task sinh mã, resource hoặc metadata có thể tạo output khác nhau nếu:

- Dữ liệu đầu vào được lấy theo thứ tự không xác định.
- Task phụ thuộc trạng thái hoặc file còn sót từ build trước.
- File được sinh từ API bên ngoài có dữ liệu thay đổi.
- Generator version khác nhau.
- Task đọc thời gian, hostname, username hoặc thư mục làm việc.
- File encoding hoặc line ending khác nhau.

Để tái lập, cần làm cho input đầy đủ và tường minh, sắp xếp dữ liệu trước khi ghi, chỉ định encoding, tránh đọc trạng thái ẩn và dùng generator version cố định.

### 9.8. Manifest và metadata phát hành

Manifest có thể chứa `Build-Jdk`, `Implementation-Version`, `Build-Time`, `Created-By` hoặc thuộc tính do plugin thêm vào. Nếu các giá trị này thay đổi, JAR khác checksum ngay cả khi `.class` giống nhau.

Hãy so sánh manifest trước khi nghi ngờ compiler. Nếu metadata cần phản ánh thời điểm hoặc builder, có thể lưu trong provenance riêng; nếu cần nằm trong JAR, phải xác định rõ giá trị có được chuẩn hóa hay không.

### 9.9. Ký số artifact

Ký JAR thêm metadata/chữ ký vào archive. Nếu quy trình ký hoặc timestamping khác nhau, file cuối cùng có thể có checksum khác dù nội dung trước khi ký giống nhau.

Khi điều tra, so sánh artifact trước bước ký nếu có thể, rồi xác minh riêng chữ ký của artifact cuối. Không chỉnh sửa JAR sau khi ký trừ khi ký lại theo quy trình hợp lệ.

## 10. Tạo archive tái lập với Gradle

Gradle cung cấp thuộc tính cho archive task để chuẩn hóa thứ tự entry và timestamp.

Ví dụ Groovy DSL:

```groovy
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType(AbstractArchiveTask).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Ví dụ Kotlin DSL:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Hai thiết lập có ý nghĩa:

- `preserveFileTimestamps = false`: không giữ timestamp gốc của file đầu vào trong archive theo cách làm archive thay đổi giữa các lần build.
- `reproducibleFileOrder = true`: sắp xếp entry theo thứ tự xác định khi đóng gói.

Các archive task hiện đại có thể đã dùng giá trị mặc định tái lập, tùy phiên bản Gradle và task. Khai báo tường minh giúp chính sách dễ nhìn và nhất quán, nhưng cần kiểm tra plugin/task tùy chỉnh có tôn trọng các thuộc tính đó hay không.

Hai thuộc tính này chỉ chuẩn hóa một phần đóng gói. Nếu task đã sinh ra file nội dung khác nhau hoặc dependency khác nhau, archive vẫn khác. Cần xử lý cả nguồn đầu vào và các task sinh file.

## 11. Tạo archive tái lập với Maven

Maven Archiver và các plugin đóng gói hỗ trợ thuộc tính `project.build.outputTimestamp` để chuẩn hóa timestamp trong archive.

Ví dụ trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.outputTimestamp>2024-01-01T00:00:00Z</project.build.outputTimestamp>
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
```

Giá trị timestamp ở ví dụ được cố định. Trong quy trình thực tế, nhóm có thể lấy một timestamp ổn định từ source revision nếu plugin và quy trình đã cấu hình hỗ trợ. Không dùng thời gian hiện tại của mỗi lần build nếu mục tiêu là byte-for-byte reproducibility.

Để kết quả ổn định hơn, cần khóa version Maven plugin và kiểm tra các plugin khác cũng tạo archive hoặc generated resource. `project.build.outputTimestamp` không tự chuẩn hóa mọi file mà một plugin bất kỳ tạo ra.

## 12. Kiểm soát dependency để hai lần build dùng cùng đầu vào

### 12.1. Dùng version cụ thể

Tránh khai báo dependency bằng version động trong build cần tái lập:

```groovy
// Dễ thay đổi theo thời điểm
implementation 'com.example:client:1.+'

// Version cụ thể
implementation 'com.example:client:1.4.2'
```

Version cụ thể làm cho yêu cầu rõ ràng hơn, nhưng repository vẫn có thể trả về artifact nội dung khác nhau nếu artifact bị thay thế. Do đó, cần kết hợp với checksum verification khi yêu cầu tính toàn vẹn cao.

### 12.2. Dependency locking

Gradle dependency locking ghi nhận version đã được chọn cho các configuration được khóa. Điều này giúp các lần build sau không tự chọn version mới chỉ vì metadata repository thay đổi.

Locking trả lời câu hỏi “version nào được phân giải?”. Nó không tự xác nhận file JAR tải về có byte giống lần trước. Để kiểm tra nội dung artifact, dùng dependency verification.

### 12.3. Dependency verification

Gradle dependency verification cho phép xác minh checksum hoặc chữ ký của dependency đã tải. Có thể tạo file metadata ban đầu bằng lệnh:

```bash
./gradlew --write-verification-metadata sha256 build
```

Gradle ghi nhận thông tin verification cho các artifact được resolve trong quá trình chạy. File thường nằm ở:

```text
gradle/verification-metadata.xml
```

Nhóm cần review metadata được tạo, xác nhận checksum/signature đúng nguồn, rồi commit file này. Khi build sau đó phân giải dependency, Gradle có thể kiểm tra artifact theo metadata đã tin cậy.

Không nên tự động tin mọi checksum được ghi nhận trong một lần build nếu nguồn repository hoặc máy build chưa được xác minh. Nếu artifact đã bị thay thế trước khi metadata được tạo, checksum mới có thể chỉ ghi nhận nội dung không mong muốn.

### 12.4. Khác biệt giữa locking và verification

| Cơ chế | Kiểm soát | Không tự giải quyết |
|---|---|---|
| Version Catalog | Nơi khai báo alias và version | Không khóa nội dung artifact tải về |
| Platform/BOM/constraints | Version tương thích hoặc ràng buộc trong graph | Không xác minh checksum artifact |
| Dependency locking | Version đã được chọn trong configuration | Không chứng minh nội dung JAR đúng |
| Dependency verification | Checksum/chữ ký artifact đã phân giải | Không tự chọn version hoặc chứng minh source build |
| Reproducible build | Khả năng tạo lại output giống nhau từ đầu vào được kiểm soát | Không tự xác nhận builder hoặc nguồn phát hành đáng tin cậy |

Các cơ chế này bổ sung cho nhau. Một build có thể dùng catalog, BOM, locking và verification cùng lúc.

## 13. Thu thập thông tin môi trường khi hai artifact khác nhau

Khi hai máy build tạo checksum khác nhau, hãy ghi lại đầu vào của từng lần build trước khi thay đổi cấu hình.

Thông tin cần so sánh:

| Nhóm | Thông tin cần ghi nhận |
|---|---|
| Source | Git commit, branch/tag, trạng thái working tree, generated source và submodule |
| Build tool | Gradle Wrapper hoặc Maven Wrapper version |
| Runtime build | JDK version, vendor, JVM options |
| Toolchain/compiler | Java toolchain, compiler release/options, annotation processor |
| Plugin | Version plugin Gradle/Maven và plugin đóng gói |
| Dependency | Version graph, lockfile, repository, checksum verification metadata |
| Hệ điều hành | OS, kiến trúc CPU, filesystem và khác biệt đường dẫn |
| Locale/time | Timezone, locale, encoding, line ending và biến môi trường liên quan |
| Build command | Task/phase, profile, project property và tham số truyền vào |
| Output | Đường dẫn, kích thước, checksum và trạng thái trước/sau khi ký |

Các lệnh cơ bản:

```bash
# Commit và trạng thái source
git rev-parse HEAD
git status --short

# Gradle và JVM đang chạy Gradle
./gradlew --version

# Maven và JVM đang chạy Maven
./mvnw --version

# Java runtime mặc định trong shell
java -version
```

Hai máy có thể dùng cùng commit nhưng working tree khác do file chưa commit, generated source hoặc file được tạo bởi script local. Vì vậy, `git status --short` là thông tin quan trọng, không chỉ `git rev-parse HEAD`.

## 14. Quy trình điều tra artifact khác checksum

Có thể dùng quy trình tuần tự sau để tránh thay đổi nhiều biến cùng lúc.

### Bước 1: xác nhận đúng hai artifact

Ghi lại đường dẫn, kích thước, loại artifact, version, classifier và trạng thái ký. Xác nhận cả hai được tạo từ cùng commit nếu đang kiểm tra reproducibility.

### Bước 2: tính lại SHA-256

Tính checksum trên cả hai file bằng cùng công cụ/thuật toán. Nếu checksum giống nhau, khác biệt quan sát ban đầu có thể do nhầm file hoặc công cụ so sánh. Nếu khác, tiếp tục.

### Bước 3: kiểm tra nguồn và cấu hình build

So sánh Git commit, working tree, Wrapper, JDK, toolchain, plugin version, project properties, build profiles và dependency locks. Xác nhận repository và dependency metadata không thay đổi.

### Bước 4: xem cấu trúc archive

Liệt kê entry bằng `jar tf`, xem timestamp/kích thước bằng `unzip -lv` hoặc công cụ ZIP tương đương. Nếu entry order hoặc timestamp khác, kiểm tra thiết lập reproducible archive.

### Bước 5: giải nén và tìm entry khác

Giải nén hai artifact vào hai thư mục riêng rồi so sánh đệ quy. Nếu chỉ manifest hoặc metadata khác, tìm task/plugin tạo metadata đó. Nếu `.class` khác, kiểm tra compiler, toolchain, annotation processor, compiler options và generated source. Nếu dependency JAR khác, kiểm tra dependency graph và repository.

### Bước 6: truy ngược nguồn tạo entry

Với từng entry khác, xác định task tạo hoặc copy nó. Kiểm tra input, output, thời gian, environment variable, locale, đường dẫn workspace và dữ liệu lấy từ hệ thống ngoài. Tìm phần đầu tiên có khác biệt thay vì chỉ xử lý file archive cuối cùng.

### Bước 7: chuẩn hóa và build lại

Sửa nguyên nhân gốc như timestamp, thứ tự file, version dependency, generator hoặc biến môi trường. Tạo hai build sạch với cùng đầu vào trong hai môi trường độc lập.

### Bước 8: xác nhận lại và lưu bằng chứng

So sánh SHA-256 lần nữa, lưu commit, build command, toolchain, dependency lock/verification metadata và checksum artifact. Nếu phát hành, xác minh chữ ký và provenance theo chính sách tổ chức.

## 15. Ví dụ điều tra một JAR khác checksum

Giả sử CI A và CI B đều build commit `abc123` và tạo `order-service.jar`. Kết quả:

```text
CI A: SHA-256 = 8f0a...a120
CI B: SHA-256 = b713...d941
```

Nhóm xác nhận cả hai working tree sạch, Wrapper và JDK giống nhau. Sau đó liệt kê entry:

```bash
jar tf ci-a/order-service.jar > entries-a.txt
jar tf ci-b/order-service.jar > entries-b.txt
diff -u entries-a.txt entries-b.txt
```

Danh sách entry giống nhau. Tiếp tục xem metadata ZIP:

```bash
unzip -lv ci-a/order-service.jar
unzip -lv ci-b/order-service.jar
```

Phát hiện timestamp của nhiều entry khác nhau. Giải nén hai archive và so sánh nội dung:

```bash
mkdir a b
unzip -q ci-a/order-service.jar -d a
unzip -q ci-b/order-service.jar -d b
diff -ru a b
```

Không có khác biệt nội dung entry. Điều này cho thấy nguyên nhân có thể nằm ở metadata archive. Nhóm chuẩn hóa timestamp và thứ tự entry trong archive task, build lại từ source giống nhau rồi tính checksum lần nữa.

Nếu sau đó checksum vẫn khác và `diff -ru` chỉ ra `META-INF/MANIFEST.MF`, nhóm cần tìm thuộc tính manifest được sinh từ build time, hostname hoặc plugin version. Nếu entry khác là `.class`, phải tiếp tục kiểm tra compiler và generated source thay vì kết luận do timestamp ZIP.

Ví dụ này cho thấy checksum là bước phát hiện, còn việc so sánh archive giúp khoanh vùng và việc truy nguồn entry mới giải thích được nguyên nhân.

## 16. Phân biệt khác biệt vô hại và khác biệt có ý nghĩa

Không phải mọi khác biệt byte đều có cùng mức độ rủi ro.

| Loại khác biệt | Ví dụ | Cách đánh giá |
|---|---|---|
| Metadata archive | ZIP timestamp, entry order, compression metadata | Có thể không ảnh hưởng hành vi, nhưng làm checksum khác và phá tính tái lập byte |
| Metadata build | Build time, hostname, Created-By | Cần xác định có chủ ý hay là thông tin môi trường bị nhúng ngoài ý muốn |
| Resource | Properties, JSON, template, service descriptor | Có thể thay đổi cấu hình hoặc hành vi runtime |
| Bytecode | `.class` khác nhau | Cần xem compiler, source, generated code và dependency API |
| Dependency | JAR thư viện hoặc version khác | Có thể thay đổi hành vi, API, bảo mật và runtime |
| Chữ ký | Entry chữ ký hoặc timestamp ký khác | Cần xác minh signer, trạng thái chữ ký và quy trình ký |

Nếu hai archive giải nén giống nhau nhưng checksum khác, chúng không giống nhau theo byte. Nếu yêu cầu phát hành là byte-for-byte reproducible, khác biệt metadata vẫn là vấn đề cần xử lý. Nếu mục tiêu chỉ là tương đương chức năng, nhóm có thể đánh giá metadata archive là khác biệt không ảnh hưởng hành vi, nhưng cần có bằng chứng và chính sách rõ ràng.

Không nên bỏ qua khác biệt trong `.class` hoặc resource chỉ vì test vẫn pass. Test có thể chưa bao phủ đường chạy bị ảnh hưởng, và một dependency khác có thể tạo ra lỗ hổng hoặc thay đổi hành vi chưa được kiểm tra.

## 17. Checksum trong quy trình phát hành và lưu trữ

Một release pipeline có thể thực hiện các bước:

```text
Checkout exact source revision
          |
          v
Build with pinned toolchain/dependencies
          |
          v
Package reproducible artifact
          |
          v
Run tests and inspect artifact
          |
          v
Sign final artifact (if required)
          |
          v
Calculate SHA-256 of final file
          |
          v
Publish artifact + checksum + provenance
```

Checksum cần được tính trên đúng file cuối cùng mà người nhận tải xuống. Nếu ký JAR sau khi tính checksum, chữ ký sẽ thay đổi file và checksum trước đó không còn đại diện cho artifact cuối.

Nên lưu cùng release:

- Tên và version artifact.
- SHA-256 của file cuối.
- Source commit hoặc tag.
- Build tool/Wrapper và JDK/toolchain.
- Dependency lock và verification metadata liên quan.
- Thông tin signer/chữ ký nếu có.
- Build provenance hoặc pipeline run ID.

Khi người nhận tải artifact, họ tính hash và so sánh với giá trị đã được cung cấp qua kênh tin cậy. Nếu có chữ ký, họ xác minh chữ ký theo trust policy của tổ chức.

## 18. Những sai lầm thường gặp

- **Cho rằng checksum khác luôn có nghĩa mã nguồn khác.** Timestamp, entry order hoặc manifest có thể làm archive khác byte.
- **Cho rằng checksum giống chứng minh artifact an toàn.** Nó chỉ chứng minh khớp với hash tham chiếu; cần nguồn tham chiếu đáng tin cậy.
- **Dùng MD5/SHA-1 cho yêu cầu xác thực mới.** Ưu tiên SHA-256 hoặc thuật toán mạnh được tổ chức chấp thuận.
- **Chỉ so kích thước file.** Hai file cùng kích thước vẫn có thể khác nội dung.
- **Chỉ xem tên entry.** Cùng danh sách entry không có nghĩa byte bên trong giống nhau.
- **Bỏ qua dependency metadata.** Cùng source nhưng dependency được phân giải khác có thể tạo artifact khác.
- **Chỉ kiểm tra Wrapper mà quên JDK và plugin.** Build tool cố định không có nghĩa compiler và mọi plugin đều giống nhau.
- **Dùng thời gian hiện tại trong generated resource.** Output sẽ thay đổi ở mỗi lần build.
- **Tính checksum trước khi ký rồi công bố cho file sau khi ký.** Hash không còn khớp artifact cuối.
- **Coi mọi khác biệt metadata là vô hại.** Cần xác định mục tiêu là byte reproducibility hay tương đương chức năng và đánh giá theo mục tiêu đó.
- **Tin checksum tải từ cùng nguồn không xác thực.** Nếu nguồn bị thay đổi, cả artifact lẫn checksum có thể bị thay thế.

## 19. Bài tập vận dụng

Một dự án Gradle build cùng commit trên hai runner. Hai file `application.jar` có kích thước bằng nhau nhưng SHA-256 khác nhau.

Hãy lập kế hoạch điều tra:

1. Cần xác nhận những thông tin nào để chắc chắn đang so sánh cùng artifact và cùng source revision?
2. Dùng lệnh nào để tính SHA-256 trên Linux, macOS và Windows?
3. Vì sao checksum khác chưa đủ kết luận bytecode khác?
4. Dùng `jar tf` và công cụ ZIP nào để so sánh danh sách entry, timestamp và kích thước?
5. Nếu giải nén hai JAR cho nội dung giống nhau, những yếu tố archive nào có thể làm checksum khác?
6. Nếu `META-INF/MANIFEST.MF` khác, cần tìm những thông tin nào được nhúng vào manifest?
7. Nếu một `.class` khác, cần kiểm tra compiler, JDK, toolchain và generated source như thế nào?
8. Gradle có thể chuẩn hóa timestamp và thứ tự archive bằng những thuộc tính nào?
9. Maven dùng property nào để đặt output timestamp ổn định?
10. Dependency locking và dependency verification khác nhau ở điểm nào?
11. Vì sao checksum không thay thế chữ ký số hoặc build provenance?
12. Nên tính checksum ở thời điểm nào nếu artifact được ký trước khi phát hành?

Thực hành bằng cách build cùng source hai lần, tính checksum, liệt kê nội dung JAR và giải nén so sánh. Sau đó thay đổi timestamp hoặc thêm một file generated chứa thời gian hiện tại để quan sát checksum thay đổi. Chuẩn hóa đầu vào, build lại và kiểm tra liệu hai artifact có cùng checksum hay không.

## 20. Nguyên tắc duy trì tính tái lập

- Dùng source revision rõ ràng và build từ working tree sạch.
- Cố định Gradle/Maven Wrapper, plugin version, JDK và compiler/toolchain.
- Quản lý dependency version bằng version cụ thể, platform/BOM và dependency locking khi phù hợp.
- Xác minh checksum hoặc chữ ký của dependency từ nguồn đáng tin cậy.
- Chuẩn hóa timestamp và thứ tự entry trong archive.
- Tránh nhúng thời gian hiện tại, hostname, username, đường dẫn workspace hoặc biến môi trường không kiểm soát vào output.
- Sắp xếp input collection và xác định encoding/line ending khi sinh file.
- So sánh artifact ở cả mức archive và mức nội dung entry.
- Tách khác biệt do đóng gói, compiler, dependency và bước ký để truy tìm đúng nguồn.
- Tính checksum sau bước cuối cùng làm thay đổi artifact và lưu giá trị cùng release metadata.
- Dùng chữ ký số và provenance khi cần xác nhận nguồn gốc artifact.

Checksum giúp trả lời liệu hai artifact có giống nhau theo byte hay không. Khi chúng khác nhau, việc kiểm tra cấu trúc archive, so sánh từng entry và đối chiếu nguồn build sẽ chỉ ra khác biệt bắt nguồn từ timestamp, metadata, dependency, compiler hay môi trường. Kết hợp các bước này giúp nhóm kiểm soát tính toàn vẹn của artifact và tiến gần hơn đến quy trình build có thể tái lập.
