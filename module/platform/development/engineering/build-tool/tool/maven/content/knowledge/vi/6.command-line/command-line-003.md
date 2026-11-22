# Truyền thuộc tính bằng -D và xử lý dấu nháy theo shell trong Maven

## 1. -D dùng để làm gì?

Trong Maven, tùy chọn dòng lệnh **`-Dten=gia-tri`** đặt một **user property** cho lần chạy Maven hiện tại. POM, profile hoặc plugin nào đọc property đó có thể sử dụng giá trị được truyền từ terminal.

~~~bash
mvn -Dbuild.environment=dev verify
mvn -Dmaven.compiler.release=17 compile
mvn -DskipTests=true package
~~~

Ba lệnh trên không làm cùng một việc: `build.environment` là property tự đặt tên và chỉ có tác dụng nếu dự án dùng nó; `maven.compiler.release` là property của Maven Compiler Plugin để cấu hình Java release; `skipTests` là property Surefire thường dùng để bỏ qua việc thực thi unit test.

Các dạng thường gặp:

~~~text
mvn -Dten=gia-tri phase
mvn -Dten1=gia-tri1 -Dten2=gia-tri2 phase
mvn -Dflag plugin:goal
~~~

`-Dflag` không có dấu `=` thường được Maven dùng như một thuộc tính kiểu bật/`true`, nhưng ý nghĩa cuối cùng còn tùy cách plugin đọc nó. Khi cần rõ ràng, nên viết `-Dflag=true` hoặc `-Dflag=false`.

**Điều quan trọng nhất:** Maven chỉ đọc các đối số mà **shell đã phân tích xong**. Nếu một giá trị chứa dấu cách nhưng không được quote đúng, Maven sẽ nhìn thấy nhiều đối số thay vì một property duy nhất.

Ví dụ sai:

~~~bash
mvn -Dgreeting=Hello Maven package
~~~

Shell thường chuyển hai đối số `-Dgreeting=Hello` và `Maven`; Maven có thể báo `Unknown lifecycle phase "Maven"`. Với Bash/Zsh, cách đúng là:

~~~bash
mvn '-Dgreeting=Hello Maven' package
~~~

Lúc này một đối số chứa cả phần `-Dgreeting=Hello Maven` được chuyển tới Maven. Dấu nháy bên ngoài chỉ dùng để điều khiển shell, thường **không** nằm trong giá trị mà Maven nhận.

## 2. Ba tầng xử lý: shell, Maven và plugin

~~~text
Lệnh gõ trong terminal
  |
  +--> [1] Shell: tách arguments, mở rộng biến, xử lý quote/ký tự đặc biệt
                     |
                     v
  +--> [2] Maven CLI: nhận "-Dgreeting=Hello Maven"
                     |
                     v
              user property greeting = "Hello Maven"
                     |
                     v
  +--> [3] POM/profile/plugin: đọc thuộc tính nếu được cấu hình sử dụng
                     |
                     v
              Kết quả build/test/package tương ứng
~~~

Điều này giải thích ba hiện tượng thường bị nhầm:

- Một lệnh **được shell chấp nhận** nhưng Maven báo phase lạ: shell đã chia arguments sai.
- Maven **nhận đúng property** nhưng build không đổi: POM/plugin không dùng property đó hoặc output chưa được tạo lại.
- Maven dùng property lúc build nhưng chương trình Java chạy sau đó không nhìn thấy nó bằng `System.getProperty`: hai quy trình truyền thuộc tính khác nhau.

Maven không tự biến một tên property bất kỳ thành cấu hình có tác dụng. `mvn -Dcolor=blue package` chỉ hữu ích khi mã cấu hình thật sự tham chiếu `color`.

## 3. User properties trong POM và plugin

Một POM có thể khai báo giá trị mặc định:

~~~xml
<properties>
    <demo.message>Hello default</demo.message>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Đây là **đoạn XML trong `<project>`**, không phải POM hoàn chỉnh. Khi Maven cần đánh giá `${demo.message}`, lệnh:

~~~bash
mvn '-Ddemo.message=Hello Maven' package
~~~

thường cho phép user property từ CLI ghi đè giá trị mặc định đã khai báo trong POM cùng tên. Tuy nhiên, **plugin chỉ thay đổi nếu tham số hoặc cấu hình của nó đọc property đó**; không nên suy rộng rằng mọi tham số đều có thể ghi đè chỉ bằng tên tùy ý.

Các ví dụ thiết thực:

| Lệnh | Điều được yêu cầu | Ghi chú |
| --- | --- | --- |
| `mvn -Dmaven.compiler.release=17 compile` | Compile theo mức Java release 17. | JDK/plugin phải hỗ trợ; không tự cài JDK 17. |
| `mvn -Dtest=CalculatorTest test` | Yêu cầu Surefire chọn test phù hợp tên. | Cần có test và Surefire được cấu hình/chạy. |
| `mvn -DskipTests=true package` | Bỏ qua thực thi unit test của Surefire. | Mã test có thể vẫn được biên dịch. |
| `mvn -Dmaven.test.skip=true package` | Bỏ qua cả biên dịch/chạy test đối với các plugin hỗ trợ. | Được Compiler Plugin, Surefire và một số plugin liên quan nhận biết. |
| `mvn -DskipITs=true verify` | Yêu cầu Failsafe bỏ qua integration test. | Hành vi còn tùy phiên bản và cấu hình Failsafe. |
| `mvn -Dtarget.env=qa verify` | Đặt property `target.env` thành `qa`. | Chỉ kích hoạt profile nếu POM có activation tương ứng. |
| `mvn -Pqa verify` | Kích hoạt profile có id `qa`. | Khác với property `-Dtarget.env=qa`. |

Không dùng `-DskipTests` như cách chứng minh mọi test (kể cả integration test) đều bị tắt: các phiên bản Failsafe mới có thể dùng `skipITs` riêng. Đọc tài liệu plugin đúng phiên bản của dự án.

## 4. Bash và Zsh: quote toàn bộ -Dkey=value

Trong Bash/Zsh trên Linux/macOS, có hai kiểu quote thông dụng:

- **Dấu đơn** `'...'`: bảo vệ nội dung literal; không mở rộng biến `$name` hay ký tự đại diện `*` ở bên trong.
- **Dấu kép** `"..."`: gom thành một đối số nhưng vẫn mở rộng một số biểu thức như `$name` hoặc command substitution.

Ví dụ giá trị có dấu cách:

~~~bash
./mvnw '-Dgreeting=Hello Maven' package
./mvnw "-Dgreeting=Hello Maven" package
~~~

Cả hai dòng trên truyền một đối số có giá trị `-Dgreeting=Hello Maven` nếu không có biểu thức đặc biệt cần mở rộng.

Ví dụ khác biệt do biến:

~~~bash
person=Lan
./mvnw "-Dgreeting=Hello $person" package
./mvnw '-Dgreeting=Hello $person' package
~~~

- Dòng dùng dấu kép truyền `Hello Lan` (shell thay `$person`).
- Dòng dùng dấu đơn truyền nguyên văn `Hello $person` (shell không thay biến).

Đối với URL có ký tự `&` và `?` hoặc mẫu có `*`, quote tránh bị shell xem là toán tử/wildcard:

~~~bash
./mvnw '-Dservice.url=https://example.org/search?q=java&lang=vi' package
./mvnw '-Dfile.pattern=*.java' package
~~~

Khi phải có dấu nháy **bên trong giá trị**, hãy phân biệt nó với dấu nháy bao đối số. Ví dụ Bash có thể giữ dấu kép literal bên trong dấu đơn:

~~~bash
./mvnw '-Dlabel=He said "Hello"' package
~~~

Ví dụ này chuyển giá trị bao gồm ký tự `"`. Nếu dấu nháy, JSON, regex hoặc shell expansion lồng nhiều lớp, ưu tiên chuyển dữ liệu sang file cấu hình hợp lệ và truyền đường dẫn đơn giản.

Lệnh nhiều dòng trong Bash/Zsh dùng dấu `\` **ngay cuối dòng**, không có khoảng trắng sau dấu:

~~~bash
./mvnw \
  '-Dgreeting=Hello Maven' \
  -Dbuild.number=42 \
  clean verify
~~~

Trên Bash/Zsh có thể có xử lý lịch sử đối với `!` trong chế độ tương tác; để giữ literal chứa ký tự đó, dấu nháy đơn thường phù hợp hơn dấu kép.

## 5. PowerShell: dấu nháy và file .cmd trên Windows

PowerShell có quy tắc chuỗi gần với Bash ở điểm: **dấu đơn** giữ literal, **dấu kép** mở rộng biến. Nhưng PowerShell dùng **backtick** làm ký tự escape và trên Windows phải chú ý lớp gọi script `.cmd`/`.bat`.

Nếu repository đã có Maven Wrapper:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd '-Dbuild.environment=dev' verify
.\mvnw.cmd '-Dgreeting=Hello Maven' package
~~~

Nếu máy có Maven hệ thống thay vì Wrapper, có thể dùng `mvn.cmd` trên Windows.

Ví dụ mở rộng biến của PowerShell:

~~~powershell
$person = 'Lan'
.\mvnw.cmd "-Dgreeting=Hello $person" package
.\mvnw.cmd '-Dgreeting=Hello $person' package
.\mvnw.cmd "-Dgreeting=Hello $env:USERNAME" package
~~~

- Dấu kép trong dòng đầu mở rộng `$person` thành `Lan`.
- Dấu đơn giữ nguyên chuỗi `$person` literal.
- `$env:USERNAME` là cú pháp lấy biến môi trường trong PowerShell.

Nếu đường dẫn đến script có dấu cách, dùng toán tử gọi `&`:

~~~powershell
& 'C:\Projects\Java Demo\mvnw.cmd' '-Dgreeting=Hello Maven' package
~~~

**Khác biệt cần nhớ:** PowerShell 7.3+ có thay đổi về native argument passing so với Windows PowerShell 5.1; script `mvnw.cmd` có thể đi qua `cmd.exe` và bị phân tích lại theo cách không giống một file `.exe`. Vì vậy với giá trị chứa nhiều dấu nháy, ký tự `%...%`, `!`, `&` hoặc `^`, cách quote thông dụng vẫn cần kiểm chứng giá trị Maven thực sự nhận. Đừng khẳng định cú pháp Bash giống PowerShell trong mọi trường hợp chỉ vì cả hai có dấu đơn.

PowerShell có stop-parsing token `--%` trên Windows, nhưng đó **không phải tùy chọn Maven** và có giới hạn về biến/escape, nên không đưa mặc định vào lệnh dùng đa nền tảng. Để viết nhiều dòng trong PowerShell, dùng ký tự backtick ngay cuối dòng; không dùng dấu `\` theo quy tắc Bash. Lệnh một dòng rõ ràng thường dễ bảo trì hơn.

## 6. CMD: dùng dấu kép, dấu đơn không bảo vệ dấu cách

Windows Command Prompt (`cmd.exe`) dùng **dấu nháy kép** `"..."` để gom đối số có khoảng trắng; dấu đơn `'...'` thường không có nghĩa quote.

~~~bat
mvnw.cmd "-Dgreeting=Hello Maven" package
mvnw.cmd "-Doutput.dir=C:\Build Reports" package
~~~

Không bê nguyên `'-Dgreeting=Hello Maven'` từ Bash sang CMD; dấu đơn có thể đi vào giá trị hoặc không bảo vệ được đối số.

CMD diễn giải một số ký tự đặc biệt (`&`, `|`, `<`, `>`, `^`, ngoặc) và hỗ trợ biến kiểu `%USERNAME%`:

~~~bat
mvnw.cmd "-Duser.name=%USERNAME%" package
~~~

`%USERNAME%` có thể được CMD mở rộng **ngay cả khi nằm trong dấu kép**. Khi delayed expansion bật, `!NAME!` cũng có thể bị diễn giải. Ngoài ra, một số quy tắc escape khác nhau giữa lệnh gõ trực tiếp trong CMD và lệnh viết trong file `.bat`; không đoán cách truyền giá trị có `%` hoặc `!` chỉ từ ví dụ Bash.

Lệnh nhiều dòng trong CMD có thể dùng dấu `^` ngay cuối dòng:

~~~bat
mvnw.cmd ^
  "-Dgreeting=Hello Maven" ^
  -Dbuild.number=42 ^
  clean verify
~~~

So sánh cùng một giá trị:

| Shell | Cách ghi | Ghi chú |
| --- | --- | --- |
| Bash/Zsh | `./mvnw '-Dgreeting=Hello Maven' package` | Dấu đơn giữ literal; dấu kép có thể mở rộng biến. |
| PowerShell | `.\mvnw.cmd '-Dgreeting=Hello Maven' package` | Dấu đơn literal; cần xét lớp `.cmd` trên Windows nếu chuỗi phức tạp. |
| CMD | `mvnw.cmd "-Dgreeting=Hello Maven" package` | Dấu kép gom đối số; `%NAME%` vẫn có thể mở rộng. |

## 7. Ví dụ Java 17: quan sát property Maven trong kết quả build

Ví dụ này cho thấy rõ `-Ddemo.message` đi từ shell qua Maven rồi vào resource của ứng dụng. Sử dụng Maven Resources Plugin với **filtering** để thay giá trị property lúc build. Không cần thư viện ngoài Java Standard Library.

Cấu trúc:

~~~text
maven-properties-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── org/example/MessageApp.java
        └── resources/
            └── app.properties
~~~

Tệp `pom.xml` hoàn chỉnh:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>org.example</groupId>
    <artifactId>maven-properties-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.message>Hello default</demo.message>
    </properties>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
                <filtering>true</filtering>
            </resource>
        </resources>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Tệp `src/main/resources/app.properties`:

~~~properties
build.message=${demo.message}
~~~

Tệp `src/main/java/org/example/MessageApp.java`:

~~~java
package org.example;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

public final class MessageApp {
    private MessageApp() {
    }

    public static void main(String[] args) throws Exception {
        Properties props = new Properties();
        try (InputStream input = MessageApp.class.getResourceAsStream("/app.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing app.properties");
            }
            props.load(new InputStreamReader(input, StandardCharsets.UTF_8));
        }

        System.out.println("build.message=" + props.getProperty("build.message"));
        System.out.println("runtime.mode=" + System.getProperty("runtime.mode", "(unset)"));
    }
}
~~~

Chạy trong **Bash/Zsh** tại thư mục có `pom.xml`:

~~~bash
mvn -B -ntp '-Ddemo.message=Hello Maven' clean package
java -Druntime.mode=dev -cp target/classes org.example.MessageApp
~~~

**Stdout chính xác của riêng lệnh `java`**:

~~~text
build.message=Hello Maven
runtime.mode=dev
~~~

Tại đây:

1. Maven nhận `demo.message=Hello Maven`.
2. Resources Plugin đọc biểu thức `${demo.message}` và tạo `target/classes/app.properties` với `build.message=Hello Maven`.
3. `MessageApp` đọc resource đã qua filtering và in kết quả.
4. `runtime.mode=dev` **được cung cấp cho JVM bằng lệnh `java`**, không phải nhờ `-Ddemo.message` lúc Maven build.

Trên Windows PowerShell (khi đã có Maven cài sẵn):

~~~powershell
mvn.cmd '-Ddemo.message=Hello Maven' -B -ntp clean package
java -Druntime.mode=dev -cp target/classes org.example.MessageApp
~~~

Trên Windows CMD:

~~~bat
mvn.cmd "-Ddemo.message=Hello Maven" -B -ntp clean package
java -Druntime.mode=dev -cp target/classes org.example.MessageApp
~~~

Nếu dự án đã thêm Maven Wrapper, có thể thay `mvn` bằng `./mvnw` ở Bash/Zsh và `mvn.cmd` bằng `.\mvnw.cmd` trên Windows.

Khi build mà **không truyền** property:

~~~bash
mvn -B -ntp clean package
java -cp target/classes org.example.MessageApp
~~~

Stdout của lệnh Java:

~~~text
build.message=Hello default
runtime.mode=(unset)
~~~

Lưu ý: để quan sát thay đổi giá trị resource, cần **build lại** sau khi đổi `-Ddemo.message`. Chạy lại riêng lệnh `java` mà không rebuild vẫn đọc resource được tạo ở lần build trước. Ví dụ này có Java 17 hợp lệ, tên class và đường dẫn nguồn thống nhất; Maven có thể cần tải plugin trong lần build đầu nếu cache chưa có.

## 8. Kiểm tra property Maven nhận với help:evaluate

Maven Help Plugin hỗ trợ goal `help:evaluate`. Ví dụ Bash:

~~~bash
mvn -q '-Dgreeting=Hello Maven' -Dexpression=greeting -DforceStdout help:evaluate
~~~

PowerShell:

~~~powershell
mvn.cmd -q '-Dgreeting=Hello Maven' -Dexpression=greeting -DforceStdout help:evaluate
~~~

CMD:

~~~bat
mvn.cmd -q "-Dgreeting=Hello Maven" -Dexpression=greeting -DforceStdout help:evaluate
~~~

Nếu lệnh thành công và đối số được truyền đúng, **giá trị được đánh giá** là `Hello Maven`. `-q` giảm log; `-DforceStdout` yêu cầu Help Plugin in giá trị ra stdout. Bản thân Maven có thể sinh thêm cảnh báo hoặc metadata tùy môi trường, nên đừng cố đối chiếu toàn bộ stdout của lệnh Maven với một chuỗi log cố định.

Đây là cách kiểm chứng quan trọng khi người dùng nghi ngờ PowerShell/`cmd.exe` đã bỏ dấu nháy, cắt khoảng trắng hoặc mở rộng biến. Một property khác cũng có thể được kiểm tra bằng cách thay `-Dexpression=greeting` thành tên cần xem.

Nếu lệnh `help:evaluate` không chạy vì Help Plugin chưa tải được, cần kiểm tra cấu hình plugin/repository và mạng; **không** tự kết luận đó là lỗi do dấu nháy.

## 9. Maven -D khác Java -D như thế nào?

Cả Maven và trình khởi chạy Java đều nhận cú pháp `-D` nhưng ý nghĩa phụ thuộc **chương trình nhận đối số**:

~~~text
mvn -Ddemo.message=Hello package
    -> User property của lần chạy Maven (POM/plugin)

java -Druntime.mode=dev -cp target/classes org.example.MessageApp
    -> JVM system property của tiến trình chạy ứng dụng
~~~

Vì vậy:

- `mvn -Dfoo=bar package` **không có nghĩa** ứng dụng khi chạy sau build tự động thấy `System.getProperty("foo")` bằng `bar`.
- Nếu Maven plugin chạy một JVM con để test/chạy app, cần cấu hình **tham số system properties của JVM con** theo plugin đó, thay vì chỉ đoán từ Maven CLI.
- Các cấu hình JVM **chạy chính Maven** thường đặt ở `MAVEN_OPTS` hoặc `.mvn/jvm.config` theo launcher và phiên bản Maven. Đó là trường hợp khác với user properties `-D` mà Maven CLI nhận.
- Nếu muốn chuyển giá trị vào artifact ở build time, cần POM/plugin có cơ chế như resource filtering; ví dụ ở mục 7 thể hiện chính xác đường đi đó.

**Một hệ quả an toàn:** Không đưa token, mật khẩu hay secret dưới dạng `-Dpassword=...` trên dòng lệnh có thể bị ghi lại trong lịch sử shell, CI log hoặc danh sách process. Dùng cơ chế secret và cấu hình an toàn được hệ thống build/CI hỗ trợ.

## 10. Giá trị rỗng, ký tự đặc biệt và nhiều lớp escape

| Trường hợp | Ý nghĩa hoặc cách xử lý |
| --- | --- |
| `-Dflag=true` | Cung cấp rõ chuỗi `true` cho property/plugin kiểu boolean. |
| `-Dflag=false` | Cung cấp rõ chuỗi `false` khi cần tắt lựa chọn. |
| `-Dflag` | Dạng viết ngắn; hành vi phụ thuộc parser/plugin, không nên lạm dụng trong tài liệu có yêu cầu chính xác. |
| `'-Dmsg='` trong Bash/PowerShell | Thử cung cấp giá trị rỗng một cách tường minh; cần xác minh plugin phân biệt rỗng và không có property. |
| `"-Dmsg="` trong CMD | Quote theo kiểu CMD cho property với phần giá trị rỗng. |
| Giá trị `a b` | Quote **toàn** `-Dkey=a b` theo quy tắc shell. |
| Giá trị chứa `&`/`|`/`;` | Quote để shell không hiểu thành toán tử; với file `.cmd` phức tạp cần test. |
| Giá trị chứa `$` trong Bash/PowerShell | Dấu đơn giúp giữ literal; dấu kép cho phép biến được mở rộng. |
| Giá trị chứa `%NAME%` trong CMD | Dấu kép **không ngăn** cơ chế mở rộng biến `%NAME%`. |
| Giá trị chứa JSON/regex/dấu nháy lồng nhau | Cân nhắc file cấu hình, vì việc escape khác nhau giữa shell và launcher. |

Lưu ý dấu nháy đơn và kép **không phải ký tự dữ liệu mặc định**: trong nhiều ví dụ chúng chỉ giúp gom đối số. Nếu muốn truyền **chính ký tự quote** vào value, cần escape theo từng shell, và trên Windows còn có thể đi qua lớp parse của `.cmd`.

Trong `pom.xml`, biểu thức `${property.name}` được Maven xử lý khi đọc/cấu hình POM hoặc plugin tương ứng; nhưng nếu gõ chính biểu thức đó trong **dòng lệnh Bash/PowerShell**, shell có thể diễn giải nó trước. Không dùng cú pháp từ XML trực tiếp trong terminal rồi mặc định nhận literal.

## 11. Khi truyền -D trên CI hoặc build script

CI cần biết đang chạy shell nào. Ví dụ GitHub Actions trên runner Ubuntu với Maven Wrapper đã commit:

~~~yaml
name: Maven CLI properties
on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Run Maven verify
        run: ./mvnw -B -ntp '-Dbuild.environment=ci' clean verify
~~~

Maven Wrapper giúp CI dùng phiên bản Maven được dự án quy định; Java 17 do `setup-java` cung cấp. Thuộc tính `build.environment` chỉ tác động đến build nếu có plugin/POM sử dụng nó.

Nếu chạy bằng biến môi trường trong Bash:

~~~yaml
- name: Build selected environment
  env:
    TARGET_ENV: staging
  run: ./mvnw -B -ntp "-Dbuild.environment=$TARGET_ENV" verify
~~~

Ở PowerShell Windows runner, biến sẽ có dạng `$env:TARGET_ENV`, còn CMD dùng `%TARGET_ENV%`. Đừng copy nguyên cú pháp Unix sang runner Windows.

Nếu nhiều build của một dự án dùng giá trị mặc định giống nhau, có thể khai báo chúng ở `<properties>` hoặc profile POM. `.mvn/maven.config` cũng hỗ trợ cấu hình các Maven CLI options cho dự án, nhưng **không phải script shell**; cú pháp tách option, dấu nháy và cách parse có thể thay đổi theo Maven version. Không đặt chuỗi quote đa tầng vào đó mà chưa thử với đúng phiên bản Maven/Wrapper.

## 12. Lỗi thường gặp và cách tìm nguyên nhân

| Hiện tượng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Unknown lifecycle phase "Maven"` | `-Dgreeting=Hello Maven` bị tách tại dấu cách. | Quote trọn đối số rồi chạy lại. |
| Giá trị nhận chỉ là `Hello` | Shell/launcher đã chia đối số. | Kiểm tra với `help:evaluate` trước khi kiểm tra POM. |
| Trong Bash, `$USER` biến thành username | Dùng dấu kép nên shell mở rộng biến. | Dùng dấu đơn nếu muốn literal. |
| Dùng dấu đơn trong CMD nhưng vẫn lỗi | CMD không coi `'...'` là cú pháp quote. | Dùng `"-Dkey=value with spaces"`. |
| Giá trị có `%USERNAME%` bị đổi trên Windows | CMD mở rộng biến ngay cả trong dấu kép. | Tránh truyền literal phức tạp qua `.cmd`; kiểm tra launcher/shell. |
| PowerShell 5.1 và 7.x cho kết quả khác nhau | Native argument passing và lớp `.cmd` khác nhau. | Kiểm tra đúng phiên bản, quote trọn đối số, dùng `help:evaluate`. |
| `-Dfoo=bar` chạy nhưng build không đổi | Plugin không dùng property `foo` hoặc chưa rebuild. | Xem cấu hình plugin/effective POM và output thật. |
| `System.getProperty("foo")` trong app là `null` | Property được truyền vào Maven, chưa truyền cho JVM app. | Dùng `java -Dfoo=bar` hoặc cấu hình plugin/runtime. |
| `-DskipTests` không tắt integration test | Surefire và Failsafe dùng các property khác nhau. | Kiểm tra tài liệu đúng phiên bản và property như `skipITs`. |
| Lệnh nhiều dòng bị cắt | Dùng sai dấu nối dòng của shell. | Bash/Zsh `\`; PowerShell dùng backtick; CMD dùng `^`. |

Cách chẩn đoán: xác nhận đang dùng **Bash, Zsh, PowerShell hay CMD** → kiểm tra lệnh có quote trọn property → dùng `help:evaluate` để xem value → kiểm tra POM/plugin có dùng property → build lại và xem output. Không in giá trị bí mật vào log trong lúc thử.

## 13. Câu hỏi tự kiểm tra

1. Trong Bash, `mvn -Dtitle=Hello World package` có thể lỗi vì sao?  
   **Đáp án:** `World` trở thành đối số/phase riêng. Sửa bằng `mvn '-Dtitle=Hello World' package`.
2. `'-Dtitle=Hello $person'` và `"-Dtitle=Hello $person"` khác gì trong PowerShell?  
   **Đáp án:** Dấu đơn giữ `$person` literal; dấu kép mở rộng biến. Với `.cmd` có thể còn cần kiểm tra parsing ở lớp Windows.
3. Trong CMD, dùng `'-Dtitle=Hello World'` có bảo vệ dấu cách không?  
   **Đáp án:** Không. Dùng `"-Dtitle=Hello World"`.
4. `mvn -Dtarget.env=qa verify` có tự kích hoạt profile `qa` không?  
   **Đáp án:** Không. Chỉ kích hoạt nếu POM khai báo activation phù hợp; `-Pqa` là cách chọn profile theo id.
5. Vì sao `mvn -Druntime.mode=dev package` không bảo đảm `System.getProperty("runtime.mode")` trong app trả về `dev`?  
   **Đáp án:** Một lệnh đặt Maven user property lúc build, còn system property của JVM ứng dụng cần được truyền ở lúc chạy hoặc qua plugin fork thích hợp.
6. Tại sao nên dùng Maven Wrapper và lệnh `help:evaluate` trên CI?  
   **Đáp án:** Wrapper giúp đồng nhất Maven version, còn Help Plugin giúp chẩn đoán xem property đến Maven có đúng sau khi shell xử lý.

## 14. Tài liệu tham khảo

- [Apache Maven — CLI Options Reference](https://maven.apache.org/ref/4-LATEST/compat/maven-embedder/cli.html).
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html).
- [Maven Compiler Plugin — Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html).
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html).
- [Maven Help Plugin — help:evaluate](https://maven.apache.org/plugins/maven-help-plugin/evaluate-mojo.html).
- [Maven Resources Plugin — Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html).
- [Microsoft Learn — PowerShell about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing).
- [Microsoft Learn — PowerShell about_Quoting_Rules](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules).
- [Microsoft Learn — cmd.exe](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd).

**Ghi nhớ:** `-D` là cơ chế đặt **Maven user property**. Shell quyết định dữ liệu nào đến Maven dưới dạng một đối số; POM/plugin quyết định thuộc tính có tác dụng gì. Dùng đúng dấu nháy của Bash/Zsh, PowerShell hoặc CMD, kiểm chứng value bằng `help:evaluate`, và phân biệt `-D` Maven với system property `-D` của JVM.
