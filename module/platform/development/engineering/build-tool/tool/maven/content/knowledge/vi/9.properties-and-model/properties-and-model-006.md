# Dùng `help:evaluate` để kiểm tra một giá trị thực tế trong Maven

## 1. Khi nhìn vào POM chưa đủ để biết Maven đang dùng giá trị nào

Một dự án Maven có thể nhận cấu hình từ `pom.xml` hiện tại, parent POM, thuộc tính trong `<properties>`, profile đang hoạt động, thông số `-D` trên dòng lệnh, thông tin Maven Settings và các giá trị mặc định. Vì vậy, **giá trị Maven thực sự nhìn thấy** có thể khác điều bạn đọc được ở một dòng trong file POM.

Một số câu hỏi thực tế:

- Artifact đang có phiên bản nào sau khi kế thừa parent POM?
- Maven nhận `groupId` và `artifactId` cuối cùng là gì?
- Thư mục `target` của project nằm ở đâu?
- Thuộc tính `maven.compiler.release` đang được tính ra là `17`, `21` hay một giá trị khác?
- Khi chạy build cho một module con, biểu thức `project.version` phản ánh module nào?
- Profile hoặc option dòng lệnh có làm thay đổi giá trị đang được dùng không?

**Maven Help Plugin** cung cấp goal **`help:evaluate`** để đánh giá **một biểu thức Maven** trong ngữ cảnh project đã chọn. Đây là cách kiểm tra tập trung trước khi suy đoán lỗi cấu hình.

Lệnh thường dùng nhất:

```bash
mvn help:evaluate -Dexpression=project.version
```

Dạng gọn, thuận tiện cho script hoặc chỉ cần kết quả:

```bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
```

Nếu POM có version `1.4.0-SNAPSHOT`, lệnh thứ hai có thể trả về đúng một giá trị:

```text
1.4.0-SNAPSHOT
```

Đó là dữ liệu do Maven đánh giá, **không phải** một dòng được sao chép thủ công từ POM.

## 2. Hiểu đúng `help:evaluate` và cách truyền expression

`help:evaluate` là **goal của Maven Help Plugin**, không phải phase trong lifecycle. Nó đánh giá expression trong ngữ cảnh Maven, có thể truy cập các thuộc tính project, một số thuộc tính Settings, system properties và user properties khi phù hợp.

Mẫu cú pháp:

```text
mvn [các-option-Maven] help:evaluate -Dexpression=<tên-biểu-thức>
```

Có bốn thành phần:

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| `mvn` | `mvn` hoặc Maven Wrapper của dự án | Chạy Maven |
| `help:evaluate` | `help:evaluate` | Goal của Maven Help Plugin |
| `-Dexpression=...` | `-Dexpression=project.version` | Yêu cầu goal đánh giá biểu thức chỉ định |
| `-q -DforceStdout` | `-q -DforceStdout` | Giảm log Maven và yêu cầu vẫn in giá trị ra stdout |

**Cú pháp quan trọng:** khi dùng tham số `-Dexpression`, bạn truyền **tên biểu thức không bao gồm cặp ký tự `${...}`**.

Đúng:

```bash
mvn help:evaluate -Dexpression=project.version
mvn help:evaluate -Dexpression=project.build.directory
```

Không nên truyền theo cách này:

```bash
mvn help:evaluate -Dexpression=${project.version}
```

Ví dụ cuối không phù hợp với định dạng tham số `expression` và có thể bị shell diễn giải đặc biệt. Cú pháp `${project.version}` thường dùng **bên trong POM hoặc ở chế độ nhập expression tương tác**; còn tham số `-Dexpression` chỉ cần `project.version`.

Nếu chạy:

```bash
mvn help:evaluate
```

Help Plugin có thể mở chế độ **tương tác**, yêu cầu bạn nhập biểu thức tại prompt. Ở đó người dùng có thể nhập `${project.version}` theo hướng dẫn của plugin. Với automation/CI, ưu tiên `-Dexpression=...` để tránh prompt chờ người dùng.

### `-q` và `-DforceStdout` giải quyết hai việc khác nhau

- `-q` (quiet) là option **toàn cục của Maven**, giảm các log `[INFO]`.
- `-DforceStdout` là **tham số của goal `help:evaluate`** (được hỗ trợ từ Maven Help Plugin 3.1.0), yêu cầu in kết quả dù Maven đang chạy quiet.
- Dùng cả hai giúp dễ đưa kết quả sang script, nhưng kết quả vẫn phụ thuộc khả năng resolve expression, môi trường và phiên bản plugin.

Không nên dùng riêng `-q` rồi thấy output trống mà kết luận thuộc tính bằng chuỗi rỗng: chính `-q` có thể đã ẩn output. Hãy dùng `-DforceStdout` cùng `-q` và kiểm tra exit code khi làm automation.

## 3. Ví dụ hoàn chỉnh: dự án Java 17 với các giá trị dễ đối chiếu

Tạo cấu trúc sau:

```text
model-check/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── App.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>model-check</artifactId>
    <version>1.4.0-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <app.channel>local</app.channel>
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
                <artifactId>maven-help-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**File `src/main/java/demo/App.java`:**

```java
package demo;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Model checked");
    }
}
```

Dự án này dùng JDK 17+ và Maven tương thích (Maven Help Plugin 3.5.2 yêu cầu Maven 3.6.3+). Lần đầu chạy Help Plugin có thể cần tải plugin/phụ thuộc của nó từ repository. Bài tập không yêu cầu dependency ứng dụng bên ngoài.

Từ thư mục `model-check/`, chạy lần lượt:

```bash
mvn -version
mvn -q help:evaluate -Dexpression=project.groupId -DforceStdout
mvn -q help:evaluate -Dexpression=project.artifactId -DforceStdout
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
mvn -q help:evaluate -Dexpression=project.packaging -DforceStdout
```

Kết quả kỳ vọng cho **bốn lệnh `help:evaluate` tương ứng**, theo đúng thứ tự:

```text
dev.example
model-check
1.4.0-SNAPSHOT
jar
```

Các dòng trên là **bốn lần chạy Maven độc lập**, không phải một lệnh tự động in bốn giá trị. Cách hiển thị dòng cuối và log tải plugin có thể khác tùy terminal; phần **giá trị** cần đối chiếu chính là nội dung được liệt kê.

Kiểm tra thuộc tính tự đặt:

```bash
mvn -q help:evaluate -Dexpression=maven.compiler.release -DforceStdout
mvn -q help:evaluate -Dexpression=app.channel -DforceStdout
```

Với POM như trên, kết quả kỳ vọng lần lượt là:

```text
17
local
```

Lệnh đầu xác nhận **giá trị thuộc tính Maven** `maven.compiler.release`, chứ chưa chứng minh JDK đang chạy Maven đúng là 17. Muốn biết Maven thực sự chạy bằng JDK nào, dùng `mvn -version` và nếu cần kiểm tra riêng `java -version`. Phiên bản Java runtime và thuộc tính biên dịch là hai khái niệm khác nhau.

### Xác minh ứng dụng thật sự build được

Chạy:

```bash
mvn clean package
java -cp target/model-check-1.4.0-SNAPSHOT.jar demo.App
```

Nếu build thành công, stdout **của ứng dụng Java** chính xác là:

```text
Model checked
```

Lệnh `java -cp` dùng classpath và tên lớp vì JAR trong ví dụ chưa được cấu hình `Main-Class`. Không mặc định sử dụng `java -jar` với JAR này.

Điểm cần phân biệt:

- `help:evaluate` chỉ **đọc và đánh giá expression**; không nhất thiết compile hay test.
- `mvn clean package` gọi lifecycle build và tạo artifact theo cấu hình.
- Xem `project.version` bằng Help Plugin không đồng nghĩa toàn bộ build sẽ thành công; vẫn có thể lỗi compile, test, plugin hoặc dependency.

## 4. Các expression hữu ích để kiểm tra một giá trị cụ thể

| Expression | Nội dung thường nhận được | Dùng khi nào |
| --- | --- | --- |
| `project.groupId` | Group ID sau khi Maven tính project model | Nghi kế thừa từ parent, tọa độ dependency sai |
| `project.artifactId` | Artifact ID của project đang chọn | Kiểm tra build nhầm module |
| `project.version` | Version cuối cùng của project | Kiểm tra parent version, CI-friendly version, release |
| `project.packaging` | `jar`, `war`, `pom`... | Muốn biết project đóng gói theo kiểu gì |
| `project.name` | Tên hiển thị của project | Kiểm tra tên mô tả, không phải artifactId |
| `project.basedir` | Đường dẫn gốc của project | Maven đang chọn POM tại thư mục nào |
| `project.build.directory` | Thư mục output build | Tìm đúng `target` hoặc output đã tùy chỉnh |
| `project.build.finalName` | Tên cơ sở của file output | Biết tên JAR/WAR mặc định hoặc đã tùy chỉnh |
| `project.build.sourceDirectory` | Đường dẫn main source | Kiểm tra project đổi layout `src/main/java` |
| `maven.compiler.release` | Thuộc tính do POM/profile/CLI khai | Kiểm tra cấu hình Java target |
| `app.channel` | Thuộc tính tùy chọn trong ví dụ | Kiểm tra property của riêng ứng dụng |
| `settings.localRepository` | Đường dẫn local repository khi biểu thức có giá trị trong settings được dùng | Tra cấu hình repository của môi trường |
| `user.home` | Thư mục home trong Java system properties | Chẩn đoán nơi Maven tra file cấu hình người dùng |

Các thuộc tính liên quan đến đường dẫn và môi trường sẽ **khác nhau giữa máy**. Với output path, bạn cần quan tâm xem đường dẫn có trỏ về đúng module hay thư mục tùy chỉnh thay vì đoán một chuỗi cố định.

Ví dụ:

```bash
mvn -q help:evaluate -Dexpression=project.basedir -DforceStdout
mvn -q help:evaluate -Dexpression=project.build.directory -DforceStdout
mvn -q help:evaluate -Dexpression=project.build.finalName -DforceStdout
```

Nếu dự án không thay đổi `<build><directory>` hoặc `<finalName>`, kết quả thứ hai thường kết thúc bằng `model-check/target` (hoặc dấu phân cách Windows tương ứng), còn kết quả thứ ba là:

```text
model-check-1.4.0-SNAPSHOT
```

Đừng gán nhầm `finalName` với `artifactId`: tên file đầu ra có thể tùy chỉnh mà không đổi GAV của artifact. Khi cần biết chính xác file JAR cuối cùng, hãy đối chiếu cấu hình plugin đóng gói và output thực tế sau build.

## 5. Khi project nằm ở một thư mục khác: kết hợp với `-f`

`help:evaluate` cần đánh giá giá trị trong **project đúng**. Nếu terminal đang ở bên ngoài `model-check/`, chỉ rõ POM:

```bash
mvn -f model-check/pom.xml -q help:evaluate -Dexpression=project.version -DforceStdout
```

Giả sử hiện tại bạn đứng trong thư mục cha chứa `model-check`, lệnh này trả về:

```text
1.4.0-SNAPSHOT
```

Ở đây:

- `-f model-check/pom.xml` chọn đúng file POM.
- `-Dexpression=project.version` chọn giá trị cần kiểm tra.
- `-q -DforceStdout` giúp in giá trị gọn.

Nếu có nhiều POM trong repository, chỉ chạy `mvn help:evaluate ...` mà không để ý CWD dễ khiến bạn đọc giá trị **của project khác**. Đây là nguồn sai lệch nguy hiểm hơn cả lỗi cú pháp, vì lệnh vẫn có thể trả ra một giá trị hoàn toàn hợp lệ.

### Dự án Maven nhiều module

Giả sử cấu trúc:

```text
shop/
├── pom.xml              # parent/aggregator
├── core/pom.xml          # module core
└── app/pom.xml           # module app
```

Muốn xem version của **module app**, cách rõ ràng là:

```bash
mvn -f shop/app/pom.xml -q help:evaluate -Dexpression=project.version -DforceStdout
```

Nếu module kế thừa version từ parent, Maven sẽ cố xây dựng effective model của module để đánh giá expression; parent cần resolve được theo cơ chế `relativePath`/repository. Vì vậy một lỗi khi parent không tìm thấy khác với việc thuộc tính `project.version` không tồn tại.

Khi gọi goal ở root aggregator và build reactor nhiều module, Maven có thể thực thi goal cho nhiều project theo ngữ cảnh, khiến output không còn là một giá trị duy nhất. Khi viết script lấy một giá trị, hãy chọn POM/module mục tiêu bằng `-f` hoặc cấu hình reactor chính xác; không mặc nhiên coi dòng đầu tiên là version mong muốn.

## 6. Vì sao giá trị thực tế có thể khác dòng bạn đang đọc?

### 6.1. Kế thừa từ parent POM

POM con có thể không khai `<groupId>` hoặc `<version>` mà kế thừa từ parent:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>shop-parent</artifactId>
        <version>2.3.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>shop-app</artifactId>
</project>
```

Đây là **đoạn POM minh họa có parent tương ứng**, chưa thể build độc lập nếu parent `shop-parent:2.3.0` không tồn tại/không thể resolve. Nếu kế thừa hợp lệ, `project.groupId` của `shop-app` thường là `dev.example` và `project.version` là `2.3.0`. Tìm `<version>` ở phần top-level của POM con mà không thấy không có nghĩa project thiếu version.

Dùng:

```bash
mvn -f shop/app/pom.xml -q help:evaluate -Dexpression=project.version -DforceStdout
```

để lấy version sau kế thừa trong môi trường mà parent resolve thành công.

### 6.2. Property và profile

Ví dụ POM có giá trị mặc định:

```xml
<properties>
    <app.channel>local</app.channel>
</properties>

<profiles>
    <profile>
        <id>staging</id>
        <properties>
            <app.channel>staging</app.channel>
        </properties>
    </profile>
</profiles>
```

Đây là **các đoạn cấu hình đặt trong `<project>`**, không phải một POM độc lập. Nếu profile `staging` được áp dụng đúng, Maven có thể đánh giá:

```bash
mvn -q help:evaluate -Dexpression=app.channel -DforceStdout
mvn -Pstaging -q help:evaluate -Dexpression=app.channel -DforceStdout
```

Thực tế mong đợi với hai trường hợp trên lần lượt là `local` và `staging`, **giả sử không có profile khác hay user property ghi đè**. Thứ tự ưu tiên và quá trình merge cấu hình cần được xét nếu nhiều nguồn cùng đặt tên property.

Một cách kiểm chứng profile là:

```bash
mvn help:active-profiles
```

Lệnh này cho biết profile nào đang hoạt động; sau đó chạy `help:evaluate` trong **cùng điều kiện option, environment và POM** để xem giá trị. Không so sánh hai lần chạy dùng profile khác nhau rồi kết luận Maven tính sai.

### 6.3. User property dòng lệnh

Nhiều cấu hình build có thể được điều khiển bằng `-Dkey=value`. Ví dụ, nếu POM dùng property `app.channel`, câu lệnh:

```bash
mvn -q help:evaluate -Dexpression=app.channel -DforceStdout -Dapp.channel=ci
```

thường thể hiện giá trị `ci` trong ngữ cảnh user property ở invocation đó. **Tham số `-Dexpression` chỉ là tham số của Help Plugin**; nó không thay đổi giá trị `project.version` hay `app.channel`, còn `-Dapp.channel=ci` là một giá trị người dùng truyền thêm vào Maven.

Đối với quá trình resolve phức tạp, không suy ra chỉ từ một biểu thức rằng tất cả plugin đều dùng giá trị đó. Hãy kiểm tra phần plugin configuration thực sự nhận được, phiên bản plugin và những điều kiện kích hoạt.

## 7. Script chỉ cần giá trị: quiet, stdout và exit code

Khi muốn xuất version để gắn nhãn artifact hoặc dùng trong bước CI, nên tránh phải lọc các dòng log `[INFO]`.

**Bash / Linux / macOS:**

```bash
VERSION="$(mvn -q help:evaluate -Dexpression=project.version -DforceStdout)"
printf '%s\n' "$VERSION"
```

Nếu lệnh Maven trả mã lỗi, script thực tế cần dừng và xử lý lỗi thay vì coi biến rỗng là version hợp lệ. Khi build phụ thuộc repository qua network, lần chạy đầu có thể tải plugin; trong CI nên pin Maven Help Plugin version và kiểm soát repository.

**PowerShell:**

```powershell
$projectVersion = (& mvn -q help:evaluate '-Dexpression=project.version' '-DforceStdout' | Out-String).Trim()
$projectVersion
```

Trong PowerShell, mã thoát của ứng dụng native có thể được kiểm tra qua `$LASTEXITCODE` sau invocation. Với automation nghiêm ngặt cần kiểm tra thành công trước khi dùng chuỗi `$projectVersion`. Khi có nhiều module/biểu thức không tồn tại, không ép lấy dòng đầu tiên cho xong.

Nếu một công cụ **chỉ** nhận path để lưu output, Help Plugin cũng có tham số `-Doutput=<file>`. Nhưng việc ghi file khi evaluate khác với việc in giá trị ra stdout; trong các script đơn giản, `-q -DforceStdout` thường đủ.

### Có nên gọi goal với tọa độ đầy đủ?

Nếu muốn tránh phụ thuộc plugin prefix hoặc phiên bản resolve, bạn có thể gọi goal bằng tọa độ đầy đủ đã pin:

```bash
mvn -q org.apache.maven.plugins:maven-help-plugin:3.5.2:evaluate -Dexpression=project.version -DforceStdout
```

Cách này hữu ích trong môi trường tự động hóa vì chỉ rõ plugin và version. Trong POM minh họa phía trên, Help Plugin `3.5.2` đã được khai nên `mvn help:evaluate` cũng dùng version đã xác định trong project đó.

## 8. `help:evaluate` khác gì `help:effective-pom` và `help:effective-settings`?

| Công cụ | Trả lời câu hỏi | Phạm vi |
| --- | --- | --- |
| `help:evaluate` | “Biểu thức `project.version` hiện bằng bao nhiêu?” | Một giá trị cụ thể |
| `help:effective-pom` | “Sau parent, profiles và quản lý plugin/dependency, mô hình POM trông thế nào?” | Bức tranh POM tổng thể |
| `help:effective-settings` | “Maven dùng các settings hiệu lực nào?” | Mô hình settings từ các nguồn cấu hình |
| `help:active-profiles` | “Profile nào đang hoạt động?” | Trạng thái profile |
| `mvn -version` | “Maven và Java runtime đang chạy là bản nào?” | Môi trường công cụ |

Nếu chỉ cần xác nhận `project.artifactId`, `help:evaluate` gọn và dễ tự động hóa. Nếu giá trị bất ngờ, mở rộng sang `help:effective-pom` hoặc xem active profiles để tìm nguồn định nghĩa.

Ví dụ:

```bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
mvn help:effective-pom
mvn help:active-profiles
```

Một giá trị được evaluate thành công không đồng nghĩa POM đã đáp ứng toàn bộ quy tắc nghiệp vụ, hoặc mọi dependency/plugin đã tải và chạy đúng. `help:evaluate` là **công cụ quan sát mô hình/thuộc tính**, không thay thế `mvn test`, `mvn verify` hay `mvn dependency:tree`.

## 9. Khi expression bị lỗi hoặc kết quả không như mong muốn

### Trường hợp 1: biểu thức không tồn tại

Ví dụ:

```bash
mvn help:evaluate -Dexpression=does.not.exist
```

Plugin có thể trả về thông tin kiểu `null object or invalid expression` hoặc kết quả không đánh giá được tùy version/điều kiện. Điều này thường có nghĩa Maven không tìm thấy expression tương ứng trong ngữ cảnh hiện tại. Không nên tự gán giá trị mặc định “0” hoặc chuỗi rỗng khi chưa hiểu nguồn.

Kiểm tra chính tả, POM được chọn, profile, parent và nguồn property. Đừng mặc định mọi key trong file XML đều có một expression với tên bạn tự đặt.

### Trường hợp 2: kết quả sai project

Bạn đứng ở monorepo root hoặc một module khác, nên `project.version` vẫn có giá trị nhưng thuộc **project khác**. Hãy đọc `project.artifactId` và `project.basedir`, sau đó chạy với `-f path/to/pom.xml`.

```bash
mvn -q help:evaluate -Dexpression=project.artifactId -DforceStdout
mvn -q help:evaluate -Dexpression=project.basedir -DforceStdout
```

### Trường hợp 3: output rỗng vì `-q`

Nếu dùng `-q` nhưng quên `-DforceStdout`, output có thể bị ẩn. Khắc phục bằng việc thêm `-DforceStdout` hoặc bỏ `-q` để xem thông báo đầy đủ.

### Trường hợp 4: lỗi tải Maven Help Plugin

Có thể do mạng, mirror, repository nội bộ, quyền truy cập, credentials hoặc phiên bản plugin. Đây là **lỗi môi trường/plugin resolution**, không phải dấu hiệu chắc chắn expression bị sai. Kiểm tra `mvn -version`, `settings.xml`, repository và log lỗi; không cần xóa toàn bộ `~/.m2/repository` khi một artifact/plugin có vấn đề.

### Trường hợp 5: giá trị không khớp POM đang xem

Cần xét thứ tự và cơ chế hợp nhất từ parent, `<properties>`, profiles, user properties, settings và default value. Chạy `help:effective-pom` rồi đối chiếu POM gốc; thử tắt/bật profile có chủ đích thay vì sửa bừa.

### Trường hợp 6: lệnh hoạt động khi chạy tương tác nhưng script kẹt

Nếu không truyền `-Dexpression`, goal có thể yêu cầu nhập từ bàn phím. Trong CI/script luôn truyền biểu thức cụ thể và xử lý exit code.

### Trường hợp 7: bạn cần xem một giá trị runtime của ứng dụng

`help:evaluate` biết các biểu thức của **Maven lúc build**. Nó **không** truy cập trạng thái runtime của Spring Boot bean, giá trị trả về của một API hay biến Java chỉ tồn tại sau khi app khởi động. Nếu bạn cần biết runtime config thực tế, dùng công cụ quan sát ứng dụng hoặc test đúng phạm vi.

## 10. Quy trình kiểm chứng một giá trị thực tế

Khi gặp câu hỏi “Maven hiện đang dùng giá trị X nào?”, thực hiện theo thứ tự:

1. **Chọn đúng project:** đứng ở thư mục có `pom.xml` hoặc dùng `mvn -f path/to/pom.xml`.
2. **Chọn một expression phù hợp:** ví dụ `project.version`, `project.build.directory` hoặc `maven.compiler.release`.
3. **Chạy lệnh đánh giá:** `mvn -q help:evaluate -Dexpression=... -DforceStdout`.
4. **So sánh với kỳ vọng và nguồn khai báo:** POM hiện tại, parent, profiles, `-D` và settings.
5. **Nếu giá trị bất ngờ:** mở `help:effective-pom`, `help:active-profiles` hoặc xem cấu hình plugin liên quan.
6. **Nếu cần chứng minh hành vi build:** chạy phase thực sự như `mvn test` hoặc `mvn clean verify`, rồi kiểm tra file output/test report. Giá trị đã đúng chưa bảo đảm mọi bước build sẽ đúng.

### Bài tập tự kiểm tra

Cho POM:

```xml
<groupId>dev.example</groupId>
<artifactId>catalog-service</artifactId>
<version>0.8.0-SNAPSHOT</version>
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Đây là **đoạn trích** cần đặt trong POM hợp lệ (không thể chạy độc lập). Giả sử không có parent/profile/user property nào thay đổi các giá trị đó.

**Câu 1:** expression nào giúp xem version của artifact?

```bash
mvn -q help:evaluate -Dexpression=project.version -DforceStdout
```

Giá trị dự kiến: `0.8.0-SNAPSHOT`.

**Câu 2:** expression nào giúp xem Java release mà POM cấu hình?

```bash
mvn -q help:evaluate -Dexpression=maven.compiler.release -DforceStdout
```

Giá trị dự kiến: `17`. Đây là **giá trị property**, không phải bằng chứng `java -version` đang dùng JDK 17.

**Câu 3:** làm sao biết đang đánh giá đúng module?

```bash
mvn -q help:evaluate -Dexpression=project.artifactId -DforceStdout
mvn -q help:evaluate -Dexpression=project.basedir -DforceStdout
```

Giá trị `project.artifactId` dự kiến là `catalog-service`; basedir là đường dẫn phụ thuộc nơi đặt module.

## 11. Những sai lầm cần tránh

**“Có thể truyền `-Dexpression=${project.version}` vì trong POM viết như vậy.”** Tham số `expression` của Help Plugin yêu cầu tên **`project.version`** không có cặp `${...}`.

**“Chỉ cần `-q` là có stdout sạch.”** Khi quiet, kết quả có thể bị ẩn. Thêm `-DforceStdout` và kiểm tra exit code nếu dùng cho script.

**“`help:evaluate` tự build project.”** Đây là plugin goal để đánh giá một expression; nó không tự đồng nghĩa chạy chuỗi compile/test/package.

**“Giá trị thấy trong POM con luôn là giá trị hiệu lực.”** Parent, profile và user properties có thể làm giá trị khác. Dùng Help Plugin để quan sát và effective POM để hiểu nguồn.

**“`project.version` là phiên bản Maven/JDK.”** Đó là version của artifact/project. `mvn -version` cho biết Maven/JDK chạy Maven; `maven.compiler.release` cho biết Java target theo property.

**“Giá trị không hiển thị thì cứ coi là null hợp lệ.”** Không. Kiểm tra expression, project, profile, log và phiên bản plugin trước khi sử dụng trong automation.

**“Gọi Help Plugin tại aggregator luôn chỉ in một giá trị.”** Không chắc; phụ thuộc phạm vi các project mà Maven thực thi goal. Khi cần một giá trị, chỉ định đúng POM/module.

## 12. Checklist sử dụng ngay

- [ ] Đang ở đúng project hoặc đã truyền `-f` chính xác.
- [ ] Expression không có cặp `${...}` trong `-Dexpression`.
- [ ] Nếu cần stdout sạch, sử dụng `-q -DforceStdout` với phiên bản Help Plugin hỗ trợ.
- [ ] Biết expression thuộc `project.*`, Maven property, Settings hay system property.
- [ ] Đã xét parent POM, active profile và những `-D` khác.
- [ ] Với giá trị đường dẫn, đối chiếu project basedir và filesystem thật.
- [ ] Với script/CI, kiểm tra exit code và dữ liệu hợp lệ trước khi dùng.
- [ ] Khi một value đúng nhưng build vẫn lỗi, tiếp tục kiểm tra plugin execution, dependency và lifecycle thật.

**Ghi nhớ:** `help:evaluate` giúp hỏi Maven **“biểu thức này hiện được đánh giá bằng gì?”**. Truyền `-Dexpression=project.version` để chọn câu hỏi; dùng `-q -DforceStdout` để đọc kết quả gọn; dùng `-f` khi cần chọn đúng project. Đây là thao tác nhỏ nhưng đặc biệt hữu ích để xác minh cấu hình thực tế thay vì suy đoán từ một dòng trong POM.

## Tài liệu chính thức

- [Maven Help Plugin — help:evaluate (3.5.2)](https://maven.apache.org/components/plugins-archives/maven-help-plugin-3.5.2/evaluate-mojo.html)
- [Maven Help Plugin — Usage](https://maven.apache.org/plugins/maven-help-plugin/usage.html)
- [Maven POM Reference](https://maven.apache.org/pom.html)
- [Maven Settings Reference](https://maven.apache.org/settings.html)
- [Maven Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
