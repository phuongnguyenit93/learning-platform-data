# Maven Plugin: executions, execution id, phase và danh sách goals

## 1. Vì sao cần cấu hình execution cho plugin?

Maven build được điều phối theo **lifecycle**, mỗi lifecycle có các **phase** (mốc xử lý) và tại từng phase có thể chạy một hoặc nhiều **plugin goal** (tác vụ thực sự do plugin cung cấp). Mỗi plugin có thể cung cấp nhiều goal; ví dụ Maven Compiler Plugin có `compile` và `testCompile`, còn Maven JAR Plugin có `jar` và `test-jar`.

Khi muốn Maven **tự gọi một goal trong quá trình build**, ta thường cấu hình **`<build><plugins><plugin><executions>`** trong `pom.xml`. Một execution mô tả: **goal nào được gọi, vào phase nào, với cấu hình nào và có ID gì để nhận diện**.

Ví dụ tối giản về hình dạng:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.2.0</version>
            <executions>
                <execution>
                    <id>say-hello</id>
                    <phase>initialize</phase>
                    <goals>
                        <goal>run</goal>
                    </goals>
                    <configuration>
                        <target>
                            <echo message="Hello from initialize"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây **chỉ là một đoạn XML bên trong `<project>`**, không phải file POM hoàn chỉnh. Với plugin ở ví dụ này, chạy `mvn initialize` hoặc phase đứng sau `initialize` trong **default lifecycle** sẽ kích hoạt execution `say-hello`, miễn Maven và plugin phân giải thành công.

**Ý chính:** `execution` không phải một phase mới. Nó là một **cấu hình liên kết goal với tiến trình build**, sử dụng phase đã tồn tại trong lifecycle. `id` chỉ là tên nhận diện execution; `goals` là danh sách tên goal của **plugin đang được khai báo**, không phải danh sách phase.

## 2. Bảng từ vựng: plugin, goal, phase, execution

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Lifecycle** | Quy trình chứa các phase theo thứ tự | `default`, `clean`, `site` |
| **Phase** | Một mốc xử lý; có thể có 0, 1 hay nhiều goal | `initialize`, `compile`, `test`, `package` |
| **Plugin** | Artifact cung cấp tập goal | `maven-antrun-plugin` |
| **Goal** | Tác vụ cụ thể của một plugin | `antrun:run`, `compiler:compile` |
| **Execution** | Một lần cấu hình cách chạy một hoặc nhiều goal trong build | `<execution>...` |
| **Execution ID** | Tên phân biệt các execution của cùng plugin, hỗ trợ merge/inheritance và log | `<id>say-hello</id>` |
| **Execution phase** | Mốc lifecycle mà goal được gắn vào | `<phase>initialize</phase>` |
| **Goals list** | Danh sách goal của plugin được thực thi khi execution chạy | `<goals><goal>run</goal></goals>` |
| **Configuration** | Tham số cấu hình cho plugin hoặc execution cụ thể | `<target><echo .../></target>` |

Ba điều dễ gây nhầm:

1. **`<goal>` chỉ ghi tên goal**, ví dụ `run`. Không ghi `<goal>antrun:run</goal>`: Maven đã biết plugin từ `<artifactId>maven-antrun-plugin</artifactId>`.
2. **`<phase>` phải là một phase Maven hợp lệ** như `initialize` hoặc `prepare-package`, không phải tên goal như `run`.
3. **`<id>` do tác giả POM đặt**, chẳng hạn `announce-initialize`. Nó không cần trùng với tên phase hoặc goal, và không làm Maven tự hiểu phải chạy lúc nào.

## 3. Cấu trúc XML chuẩn của một plugin có nhiều executions

Một plugin có thể chứa **nhiều execution**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>

    <executions>
        <execution>
            <id>first-job</id>
            <phase>initialize</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="First job"/>
                </target>
            </configuration>
        </execution>

        <execution>
            <id>second-job</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Second job"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn `<plugin>` để chèn vào `<build><plugins>`**, không phải một POM độc lập. Execution thứ nhất chạy khi default lifecycle đến `initialize`; execution thứ hai chạy khi đến `prepare-package`. Cả hai cùng sử dụng goal `run` nhưng với **configuration riêng**.

Quy tắc XML:
- `<executions>` chứa **nhiều** `<execution>`.
- Mỗi `<execution>` chứa `<id>`, thường có `<phase>`, danh sách `<goals>` và `<configuration>` nếu goal cần.
- `<goals>` có một hoặc nhiều `<goal>`.
- `<configuration>` có thể nằm ở **cấp plugin** (dùng chung) và/hoặc **cấp execution** (tùy chỉnh riêng).
- Mọi execution thuộc **plugin khai báo ngay bên ngoài**; không lồng một `<plugin>` vào `<execution>`.

Đừng khai báo lại cùng một plugin trong `<build><plugins>` thành hai khối trùng `groupId/artifactId` chỉ để có hai execution. Cách đúng là **một plugin, nhiều execution**. Maven 3 có thể cảnh báo đối với khai báo plugin trùng; Maven 4 kiểm tra nghiêm hơn.

## 4. Phase điều khiển lúc nào goal được chạy

Trong **default lifecycle** của Maven, các mốc quan trọng theo thứ tự là:

```text
validate
   |
initialize
   |
generate-sources
   |
process-resources
   |
compile
   |
test-compile
   |
test
   |
prepare-package
   |
package
   |
verify
   |
install
   |
deploy
```

Đây chỉ là **một số phase nổi bật**, không phải danh sách đầy đủ. Giữa các mốc còn nhiều phase khác. Khi chạy `mvn package`, Maven đi qua các phase từ `validate` tới `package` theo thứ tự; ở mỗi phase có goal được gắn thì Maven chạy chúng.

Ví dụ execution ở `initialize`:

```xml
<execution>
    <id>prepare-environment</id>
    <phase>initialize</phase>
    <goals>
        <goal>run</goal>
    </goals>
    <configuration>
        <target>
            <echo message="Preparing build environment"/>
        </target>
    </configuration>
</execution>
```

Khi thực thi:
- `mvn validate`: **chưa đến** `initialize`, nên execution này không chạy.
- `mvn initialize`: đã đến `initialize`, execution chạy.
- `mvn test`: đi qua `initialize` trên đường tới `test`, execution chạy.
- `mvn package` hoặc `mvn verify`: cũng đi qua `initialize`, execution chạy.

**Một execution không mặc định chỉ chạy khi gõ đúng tên phase đó.** Nó chạy khi lifecycle **đi qua** phase được gắn, miễn không bị skip/bỏ qua vì cấu hình plugin hay build thất bại trước khi tới đó.

### Đừng nhầm clean lifecycle

`mvn clean` thuộc **clean lifecycle**, không tự chạy `initialize` của default lifecycle. `mvn clean package` yêu cầu **hai việc theo thứ tự**: chạy tới `clean` trong clean lifecycle, rồi chạy tới `package` trong default lifecycle.

Không nên tự gắn goal xử lý nguồn vào phase `clean` nếu mục tiêu thật sự thuộc default lifecycle. Luôn chọn phase theo **mốc cần có input và mốc cần output**, tránh tạo artifact quá sớm hoặc quá muộn.

## 5. execution id: định danh, log và cấu hình kế thừa

Một execution ID nên có ý nghĩa cụ thể:

```xml
<id>generate-client-sources</id>
```

Nó có ba vai trò chính:

1. **Phân biệt nhiều execution của cùng một plugin trong cùng POM.** Ví dụ `announce-initialize` khác `announce-prepare-package`.
2. **Giúp nhận diện khi xem Maven log**. Dòng log plugin thường chứa execution ID trong ngoặc, ví dụ `(announce-initialize)`.
3. **Làm khóa khi Maven hợp nhất cấu hình qua parent/child POM hoặc profile**: các execution có ID giống nhau có thể được match để merge/override theo quy tắc Maven model, trong khi ID khác nhau tạo các execution riêng.

**Lưu ý về tính duy nhất:** các execution ID phải **duy nhất trong các execution của cùng plugin trong một POM**. Không phải unique toàn repository: nhiều plugin khác nhau có thể có ID `verify-metadata`; một POM con có thể cố ý dùng cùng ID với execution của parent để tinh chỉnh cấu hình được kế thừa.

Không dùng tất cả execution cùng ID `default`. ID rõ nghĩa dễ debug và tránh xung đột khi parent hoặc profile bổ sung execution.

### Ví dụ parent/child dùng cùng ID

Parent POM có thể định nghĩa một execution:

```xml
<execution>
    <id>check-generated-files</id>
    <phase>verify</phase>
    <goals>
        <goal>run</goal>
    </goals>
</execution>
```

Child POM muốn thay một số tham số execution **có thể dùng cùng ID** `check-generated-files` trong cùng plugin. Maven áp dụng **quy tắc model merge** cho phần khai báo parent/child thay vì mặc nhiên tạo thêm một execution độc lập. Một execution có ID **khác** sẽ được giữ như một execution khác.

Đây chỉ là ví dụ **cấu trúc/merge**: goal `antrun:run` thực tế còn cần cấu hình `target` phù hợp nếu muốn thực thi công việc. Không copy trích đoạn parent này thành một build hoàn chỉnh.

Nếu không muốn một plugin/execution ở parent truyền xuống child, Maven còn hỗ trợ `<inherited>false</inherited>` tại nơi phù hợp. Nên đọc Effective POM để xác định đúng điều gì thực sự được kế thừa, vì việc hợp nhất cấu hình có thể chi tiết hơn “con thay hết cha”.

## 6. Danh sách goals: một execution có thể làm nhiều việc

Cấu trúc `<goals>` chứa **các tên goal** của plugin:

```xml
<goals>
    <goal>tree</goal>
    <goal>analyze-only</goal>
</goals>
```

Hai goal trên thuộc **Maven Dependency Plugin** (`maven-dependency-plugin`), không thuộc AntRun. Ví dụ đầy đủ về việc buộc **hai goal có thật của cùng plugin** vào một phase:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-dependency-plugin</artifactId>
    <version>3.11.0</version>
    <executions>
        <execution>
            <id>verify-dependency-usage</id>
            <phase>verify</phase>
            <goals>
                <goal>tree</goal>
                <goal>analyze-only</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn cấu hình tùy chọn để đặt trong `<build><plugins>`**, không phải phần có sẵn trong POM thực hành chính. Nó yêu cầu goal `dependency:tree` và `dependency:analyze-only` chạy khi lifecycle đến `verify`, theo thứ tự khai báo trong `<goals>`. Kết quả có thể cảnh báo dependency chưa dùng hoặc chưa khai báo; hai goal cần Maven phân giải được Dependency Plugin và project dependencies.

**Phân biệt hai cách tổ chức:**
- **Một execution, nhiều goals**: dùng khi các goal chia sẻ mốc phase, ID và phần cấu hình chung.
- **Nhiều execution cho cùng plugin**: dùng khi goal cần chạy ở **phase khác nhau**, hoặc cùng phase nhưng cần **configuration/ID khác nhau**, hoặc muốn điều khiển thứ tự rõ ràng.

Không thể dùng tên tùy ý trong `<goal>` như `build-everything` nếu plugin không cung cấp goal đó. Đọc plugin descriptor/docs để biết goal hợp lệ.

## 7. Configuration cấp plugin so với configuration cấp execution

Ví dụ plugin có cấu hình chung:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>

    <configuration>
        <skip>false</skip>
    </configuration>

    <executions>
        <execution>
            <id>announce-step-a</id>
            <phase>initialize</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Step A"/>
                </target>
            </configuration>
        </execution>
        <execution>
            <id>announce-step-b</id>
            <phase>prepare-package</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Step B"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Ý nghĩa:
- Cấp plugin chứa `skip=false` được chia sẻ cho những invocation thích hợp.
- Cấp execution `announce-step-a` có Ant `target` riêng.
- Cấp execution `announce-step-b` có Ant `target` khác.
- Nếu cùng một tham số xuất hiện ở cả hai cấp, cấu hình cấp execution có thể override/merge cấu hình chung theo quy tắc Maven và kiểu tham số. Không suy luôn là “copy đè nguyên XML” đối với mọi phần tử phức tạp.

**Tránh thay đổi cấu hình global chỉ để sửa một execution** nếu plugin đang được dùng ở nhiều phase. Khi cần khác nhau giữa các lần chạy, cấu hình ở đúng `<execution>` thường dễ hiểu hơn.

Một cảnh báo quan trọng: `<configuration>` là tham số của **goal/plugin cụ thể**. Không phải plugin nào cũng có `skip` hay `target`. Những thẻ trên hợp lệ với AntRun Plugin trong ví dụ, không phải các thẻ phổ quát của mọi plugin Maven.

## 8. Ví dụ thực hành Java 17 hoàn chỉnh với ba executions

Để nhìn thấy **ID, phase và thứ tự goal** trong log, ta tạo một ứng dụng Java nhỏ và gắn ba execution của **Apache Maven AntRun Plugin 3.2.0**. AntRun có goal `run`, nhận Ant `target` chứa các tác vụ như `echo`.

Các execution:
- `announce-initialize` chạy ở `initialize`;
- `announce-prepare-a` chạy ở `prepare-package`;
- `announce-prepare-b` cũng chạy ở `prepare-package` nhưng đứng **sau** `announce-prepare-a` trong POM.

### 8.1. Cấu trúc dự án

```text
maven-executions-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/executions/App.java
```

File Java phải đặt đúng package directory `com/example/executions`. Ví dụ dùng JDK 17+, Maven 3.9.x (hoặc phiên bản đáp ứng yêu cầu AntRun Plugin) và quyền tải plugin từ repository nếu chưa cache.

### 8.2. pom.xml đầy đủ

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>maven-executions-demo</artifactId>
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
                <version>3.14.1</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.4</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
                <executions>
                    <execution>
                        <id>announce-initialize</id>
                        <phase>initialize</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="LAB initialize: announce-initialize"/>
                            </target>
                        </configuration>
                    </execution>

                    <execution>
                        <id>announce-prepare-a</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="LAB prepare-package: announce-prepare-a"/>
                            </target>
                        </configuration>
                    </execution>

                    <execution>
                        <id>announce-prepare-b</id>
                        <phase>prepare-package</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="LAB prepare-package: announce-prepare-b"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Đây là **POM hoàn chỉnh**, không cần chèn thêm phần tử `<project>` hoặc `<build>` bên ngoài.

Những ràng buộc:
- `jar` packaging gắn các goal Maven mặc định vào `compile`, `test` và `package`.
- Maven Compiler Plugin có version cố định và dùng Java release `17`.
- Maven Surefire Plugin có version cố định. Vì ví dụ không có test source, nó có thể báo không có test cần chạy; đây không phải lỗi về execution AntRun.
- Maven JAR Plugin có version cố định để tạo JAR chính.
- AntRun Plugin 3.2.0 được ghim version và xuất hiện **một lần** trong `<plugins>`, chứa **ba execution** khác ID.
- Mỗi execution cấu hình `<target><echo>` riêng để log có dấu hiệu quan sát rõ.
- Hai execution ở `prepare-package` được liệt kê theo thứ tự A rồi B; chúng chạy theo thứ tự này trong mô hình Maven 3 thông thường.

### 8.3. src/main/java/com/example/executions/App.java

```java
package com.example.executions;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Java 17 execution demo");
    }
}
```

Đây là mã Java 17 hoàn chỉnh. Class không dùng AntRun trực tiếp: AntRun chạy trong **Maven build**, còn chương trình Java chạy riêng sau khi biên dịch. Nhờ vậy ta tách biệt “dòng log của plugin” khỏi “stdout của ứng dụng”.

### 8.4. Chạy validate

```bash
mvn -B -ntp validate
```

Kết quả mong đợi: Maven xử lý POM tới phase `validate`; **không có** các thông báo AntRun `LAB initialize` hoặc `LAB prepare-package` vì chưa đi tới `initialize`.

### 8.5. Chạy initialize

```bash
mvn -B -ntp initialize
```

Lúc này Maven đi qua `validate` và tới `initialize`. Execution `announce-initialize` chạy; ta kỳ vọng thấy **nội dung thông báo**:

```text
LAB initialize: announce-initialize
```

Nội dung trên chỉ là **marker do Ant `echo` phát ra**, không phải stdout Maven nguyên văn: thực tế log có thể kèm `[INFO]`, `[echo]`, dòng tên plugin/ID và thời gian.

Hai execution `announce-prepare-a`/`announce-prepare-b` **chưa chạy**.

### 8.6. Chạy test

```bash
mvn -B -ntp test
```

Maven đi qua `initialize` để tới `test`, nên **marker initialize lại xuất hiện trong lượt Maven mới**. Nhưng `prepare-package` nằm sau `test`, vì vậy hai execution chuẩn bị package không xuất hiện.

Nếu chưa có test classes, Surefire có thể báo “No tests to run”; vẫn có thể hoàn tất phase `test`. Không kết luận AntRun lỗi chỉ vì không có test JUnit trong dự án mẫu.

### 8.7. Chạy package và quan sát thứ tự

```bash
mvn -B -ntp clean package
```

`clean` xóa output build cũ trong clean lifecycle, sau đó default lifecycle chạy từ đầu tới `package`. Ba marker AntRun **xuất hiện theo thứ tự**:

```text
LAB initialize: announce-initialize
LAB prepare-package: announce-prepare-a
LAB prepare-package: announce-prepare-b
```

Đây là **ba marker theo thứ tự xuất hiện**, không phải toàn bộ console output liền ba dòng: giữa chúng có thể có nhiều dòng log tài nguyên, compiler, test và JAR Plugin.

Kết quả build thành công thông thường có file:

```text
target/classes/com/example/executions/App.class
target/maven-executions-demo-1.0.0.jar
```

Để chạy chương trình ứng dụng, từ thư mục chứa POM:

```bash
java -cp target/classes com.example.executions.App
```

**Stdout chính xác của lệnh `java`:**

```text
Java 17 execution demo
```

Không dùng `java -jar target/maven-executions-demo-1.0.0.jar` trừ khi đã cấu hình `Main-Class` trong manifest. POM mẫu chưa cấu hình manifest main class, nên dùng classpath như trên.

### 8.8. Chạy verify

```bash
mvn -B -ntp verify
```

Maven đi qua `initialize` và `prepare-package` trên đường tới `verify`, nên các marker trên đều xuất hiện trong lượt chạy này. Nhưng **không có execution mới gắn trực tiếp với `verify`** trong POM mẫu; sau `package` Maven vẫn đi qua các phase tiếp theo tới `verify`.

Thời gian chạy, số lượng plugin goal khác và thông tin tải dependency có thể thay đổi, nhưng **logic chọn execution theo phase** phải nhất quán với cấu hình.

## 9. Hai executions trong cùng phase chạy theo thứ tự nào?

Với cùng một plugin, Maven cho phép nhiều execution gắn vào `prepare-package`:

```xml
<execution>
    <id>step-a</id>
    <phase>prepare-package</phase>
    <goals><goal>run</goal></goals>
</execution>
<execution>
    <id>step-b</id>
    <phase>prepare-package</phase>
    <goals><goal>run</goal></goals>
</execution>
```

Đây là đoạn **cấu trúc minh họa**: nếu dùng AntRun như POM chạy được thì mỗi execution cần `<configuration><target>...` tương ứng.

Theo Apache Maven, **nhiều execution được gắn vào cùng phase** được gọi theo **thứ tự khai báo** trong POM, sau khi Maven xử lý kế thừa/model phù hợp. Trong POM chạy được, `announce-prepare-a` đứng trước `announce-prepare-b` nên marker A xuất hiện trước marker B.

Có một số điểm tinh tế:
- **Thứ tự phase luôn quan trọng trước.** Execution ở `initialize` chạy trước `prepare-package` dù được viết ở vị trí thấp hơn trong phần XML.
- Trong một phase, mục tiêu được binding mặc định bởi packaging có thể chạy **trước** những goal người dùng bổ sung trong POM.
- Khi có inherited executions từ parent và execution từ child, Maven phải merge model; các execution riêng thường theo thứ tự **parent trước child**, trừ trường hợp ID trùng làm cấu hình bị merge/override.
- Với nhiều plugin hoặc packaging khác, cần đọc **effective model và build log thực tế**; không nên dùng bảng XML tự viết để tuyên bố một thứ tự chạy bất biến trên mọi Maven.
- Maven 4 có bổ sung cú pháp thứ tự phase với số trong dấu ngoặc vuông, ví dụ `test[100]`; **không đem cú pháp đó vào POM Maven 3** của bài này. Nếu target Maven 4, đọc chính xác tài liệu phiên bản đang dùng.

**Không tạo phụ thuộc ẩn giữa hai goal** nếu một plugin có thể gọi chúng độc lập hoặc nếu thay đổi thứ tự POM làm kết quả hỏng. Khi một goal cần output của goal khác, nên chọn phase đúng và mô tả dependency của pipeline rõ ràng.

## 10. Bỏ phase: goal có default phase hay không?

Một execution có thể không khai báo `<phase>`:

```xml
<execution>
    <id>attach-extra-artifact</id>
    <goals>
        <goal>test-jar</goal>
    </goals>
</execution>
```

Đây là **một execution của Maven JAR Plugin**, không phải của AntRun; phải đặt trong plugin `maven-jar-plugin` tương ứng. Goal `jar:test-jar` có **default phase `package`** theo metadata plugin, nên Maven có thể liên kết execution này với `package` dù không ghi `<phase>`.

Ngược lại:
- Nếu goal **có default phase**, Maven có thể dùng default phase của goal khi execution thiếu `<phase>`.
- Nếu goal **không có default phase** và execution không chỉ định `<phase>`, nó thường **không được chạy như một phần của lifecycle bình thường**. Goal có thể vẫn được gọi trực tiếp bằng CLI.
- Không phải tất cả goal của một plugin có cùng default phase.
- Nếu một execution có nhiều goals với những default phase khác nhau, hãy **đặt `<phase>` tường minh** và kiểm tra plugin docs thay vì suy đoán từ tên goal.

Từ đó có một quy tắc soạn POM: với goal không có lifecycle binding rõ ràng hoặc có thể gắn vào nhiều phase, **ghi rõ `<phase>`** để hành vi dễ đọc và tái lập. Ví dụ AntRun của bài học cố ý đặt phase tường minh cho cả ba execution.

## 11. Gọi phase và gọi plugin goal trực tiếp là hai việc khác nhau

Ví dụ trong POM bài học:

```bash
mvn package
```

Lệnh này chạy default lifecycle tới `package`, nên ba execution AntRun đã gắn phase sẽ chạy trên đường đi.

Nhưng:

```bash
mvn antrun:run
```

Lệnh này yêu cầu **goal `run` trực tiếp**. Nó không có nghĩa “chạy tất cả execution của AntRun theo phase”, cũng không tự yêu cầu default lifecycle đến `package`. Do `<target>` được đặt riêng trong các execution của POM mẫu, một invocation trực tiếp không mang đúng configuration có thể không thực hiện việc bạn trông đợi.

Từ Maven 3.3.1, Maven hỗ trợ gọi **goal trực tiếp với execution ID** qua cú pháp `goal@executionId`:

```bash
mvn org.apache.maven.plugins:maven-antrun-plugin:3.2.0:run@announce-initialize
```

Lệnh này nhắm execution `announce-initialize` và sử dụng cấu hình liên quan. **Đây là direct goal invocation**, không phải yêu cầu Maven chạy toàn bộ default lifecycle đến `initialize`; với goal phụ thuộc output từ phase trước, cần đảm bảo điều kiện đầu vào bằng cách phù hợp.

So sánh:

| Lệnh | Ý nghĩa |
| --- | --- |
| `mvn initialize` | Đi từ đầu default lifecycle đến `initialize`; chạy execution gắn ở phase đó |
| `mvn package` | Đi tới `package`; kích hoạt execution ở các phase đứng trước/đến package |
| `mvn antrun:run` | Chạy trực tiếp goal `run`, không mặc định phát lại các execution lifecycle |
| `mvn antrun:run@announce-initialize` | Gọi trực tiếp goal với cấu hình execution có ID tương ứng |
| `mvn clean package` | Chạy clean lifecycle rồi default lifecycle tới package |
| `mvn -B -ntp verify` | Chạy tới verify; `-B/-ntp` chỉ điều chỉnh tương tác/hiển thị tiến độ |

Không dùng `mvn initialize prepare-package package` như cách “ép” Maven chạy từ đầu một lần: mỗi phase target là một yêu cầu CLI có thể khiến các phase đứng trước được duyệt lại; thông thường **chỉ cần gọi phase cuối cần đạt**.

## 12. pluginManagement khác build/plugins như thế nào?

Hai vùng XML có tên plugin nhưng mục đích khác nhau:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
            </plugin>
        </plugins>
    </pluginManagement>

    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <executions>
                <execution>
                    <id>announce-initialize</id>
                    <phase>initialize</phase>
                    <goals><goal>run</goal></goals>
                    <configuration>
                        <target>
                            <echo message="Managed plugin version"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là đoạn `<build>` minh họa, không phải một POM hoàn chỉnh và **không cần chèn thêm** vào POM ở mục 8.

- `<pluginManagement>` quản lý version, configuration và execution defaults cho plugin **khi plugin được dùng**. Đưa AntRun vào đây **không tự đảm bảo** một execution mới sẽ chạy ở mọi module.
- `<build><plugins>` là nơi plugin được khai báo để sử dụng trong build của project. Execution AntRun ở ví dụ được đặt ở đây, nên goal `run` được gắn vào lifecycle.
- Với plugin đã được packaging/lifecycle gắn mặc định như compiler cho `jar`, pluginManagement có thể điều chỉnh version/configuration của plugin được gọi.
- Một parent POM thường dùng pluginManagement để giữ versions nhất quán cho nhiều child POM; child chọn plugin/execution cần dùng trong `build/plugins`.

Để biết plugin và execution nào thực sự hiện diện sau inheritance/management, dùng `help:effective-pom` và quan sát build log. Chỉ nhìn một khối `pluginManagement` không chứng minh goal đã được gọi.

## 13. Inheritance, profiles và execution ID trùng nhau

Một parent POM có thể định nghĩa:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <executions>
        <execution>
            <id>shared-check</id>
            <phase>verify</phase>
            <goals><goal>run</goal></goals>
        </execution>
    </executions>
</plugin>
```

Một POM con có thể định nghĩa **cùng plugin và cùng ID** `shared-check` để thay đổi `phase`, `configuration` hoặc những trường được Maven merge. Nếu POM con dùng ID khác, nó thường tạo **execution bổ sung**, không sửa execution của parent.

Nguyên tắc:
- **ID giống nhau giữa parent và child:** Maven match và merge/override execution theo model builder, cấu hình của child có ưu tiên thích hợp.
- **ID khác nhau:** cả hai execution có thể cùng tồn tại trong effective model, dẫn đến hai lần thực thi.
- **`<inherited>false</inherited>`:** hạn chế kế thừa plugin hoặc execution tương ứng theo vị trí đặt.
- **Profile:** execution từ profile đang active có thể tham gia merge; execution ở profile **không active** không được đưa vào build chỉ vì xuất hiện trong source POM.

Không kết luận một execution bị nhân đôi hay biến mất chỉ bằng số lượng đoạn XML trong hai POM nguồn. **Sinh effective POM cho đúng module và đúng tập active profiles**, sau đó kiểm tra log phase để biết kết quả.

## 14. Kiểm tra execution nào Maven thực sự sử dụng

### 14.1. Xem log bình thường

```bash
mvn -B -ntp clean package
```

Maven thường ghi tên plugin, version, goal và execution ID trong dòng tương tự:

```text
--- antrun:3.2.0:run (announce-initialize) @ maven-executions-demo ---
--- antrun:3.2.0:run (announce-prepare-a) @ maven-executions-demo ---
--- antrun:3.2.0:run (announce-prepare-b) @ maven-executions-demo ---
```

Đây là **trích đoạn mang tính minh họa**, không phải log nguyên văn từ một lượt chạy; prefix `[INFO]`, formatting và các dòng xen giữa tùy bản Maven.

### 14.2. Xem Effective POM

```bash
mvn help:effective-pom -Doutput=effective-pom.xml
```

Tìm `maven-antrun-plugin` trong `<build><plugins>` và các `<executions>`. Xem ID/phase/goals, kiểm tra có bị parent/profile ghi đè hoặc thêm execution ngoài dự kiến không.

Có thể bật verbose của Maven Help Plugin phiên bản hỗ trợ:

```bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=effective-verbose.xml
```

Chú thích XML giúp truy dấu nguồn khai báo, nhưng **Effective POM không phải một bản ghi bảo đảm tất cả goal đã thực thi thành công**. Goal có thể bị skip, build dừng do lỗi, hoặc CLI chỉ chạy đến phase trước đó. Phải xem lệnh thực tế và log.

### 14.3. Xem goal metadata

Để xem thông tin chi tiết về goal `run` của AntRun:

```bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-antrun-plugin -Dgoal=run -Ddetail
```

Goal metadata có thể nêu các tham số được hỗ trợ, default phase, yêu cầu Maven/JDK và kiểu invocation. Khi kiểm tra chuyện bỏ `<phase>`, **đọc mục default phase của đúng goal** thay vì tự suy từ tên.

### 14.4. Debug khi cần

```bash
mvn -X -B -ntp package
```

Debug mode cung cấp thêm thông tin build plan, cấu hình goal và dependencies. **Không sử dụng log debug chưa lọc trong kênh công khai**: plugin và môi trường có thể ghi ra URL repository nội bộ, property hoặc thông tin nhạy cảm.

## 15. Lỗi cấu hình thường gặp và cách sửa

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Plugin được khai báo nhưng không thấy goal chạy | Chỉ thêm plugin/version, chưa có execution/goals hoặc goal không có binding mặc định | Thêm `<executions>` và `<goals>` hợp lệ vào `build/plugins` |
| Execution có `id` nhưng Maven không gọi | `id` chỉ là nhãn, thiếu `phase` và goal không có default phase | Đặt `<phase>` đúng và xem plugin docs |
| `mvn validate` không có marker AntRun | Execution gắn vào `initialize` đứng sau validate | Chạy `mvn initialize` hoặc phase sau |
| `mvn test` chưa có marker prepare-package | `prepare-package` đứng sau `test` | Chạy `mvn package` |
| Không thấy marker `announce-prepare-b` | Build lỗi trước phase, execution bị skip hoặc POM không chứa execution sau merge | Xem log lỗi, effective POM và đúng module |
| `MojoNotFoundException` hoặc goal không tồn tại | Ghi sai tên `<goal>` hoặc dùng goal của plugin khác | Xem goal list của đúng plugin |
| AntRun không thấy `target` | Configuration đặt sai cấp hoặc gọi goal trực tiếp không dùng execution đã cấu hình | Kiểm tra `<configuration><target>` và `run@executionId` |
| Execution chạy hai lần ngoài dự kiến | Có hai ID khác nhau cùng gắn goal vào phase hoặc CLI gọi phase nhiều lần | Kiểm tra effective POM, lệnh Maven và IDs |
| Lỗi duplicate execution ID | Hai execution của cùng plugin trong một POM trùng ID | Đặt ID riêng hoặc dùng cơ chế parent-child merge có chủ đích |
| Hai khối plugin cùng artifactId | Khai báo plugin bị lặp trong `<plugins>` | Hợp nhất thành một plugin với nhiều executions |
| Thứ tự mục cùng phase khác dự đoán | Có lifecycle default goal, inherited execution, profile hoặc Maven version khác | Đọc effective model và log thực tế; kiểm tra thứ tự POM |
| Cấu hình parent không được kế thừa | `<inherited>false</inherited>` hoặc pluginManagement chưa được kích hoạt sử dụng | Kiểm tra effective POM của module con |
| `mvn antrun:run` không giống `mvn package` | Direct goal không tự chạy toàn bộ lifecycle/bindings | Dùng phase hoặc `goal@executionId` phù hợp |
| Plugin goal fail làm build dừng | Ant task/goal lỗi hoặc thiếu dependency/permission | Sửa lỗi goal đầu tiên; đừng mặc định skip để che lỗi |
| Maven dùng sai phiên bản plugin | Chưa pin version hoặc parent/pluginManagement khác | Ghim version tương thích và kiểm tra effective POM |
| `-Pprofile` có execution nhưng không chạy | Profile không active trong đúng lượt hoặc gắn phase chưa đạt | Chạy `help:active-profiles` với cùng `-P`, xem phase |
| Lệnh chạy đúng phase nhưng Java source chưa có | Goal sinh source gắn quá muộn, ví dụ sau `compile` | Đưa goal sinh source vào `generate-sources` và thêm source root phù hợp |

**Cẩn thận với việc dời phase:** một goal cần các lớp Java đã biên dịch **không nên** gắn vào `generate-sources` nếu input của nó nằm trong `target/classes`. Ngược lại, goal sinh source để Compiler Plugin sử dụng phải chạy **trước compile**, thường ở `generate-sources`, và có thể cần plugin bổ sung source root. Chọn phase theo dữ liệu đầu vào/đầu ra, không theo sở thích tên gọi.

## 16. Nguyên tắc viết executions dễ bảo trì

1. **Tên ID biểu đạt mục đích**, ví dụ `generate-openapi-client`, `attach-test-fixtures`, `verify-license-header`, không dùng `run1`/`run2` nếu có thể đặt nghĩa rõ.
2. **Ghim version plugin** trong POM hoặc parent pluginManagement để build tái lập.
3. **Gắn goal vào phase sớm nhất mà input đã sẵn sàng**, nhưng không sớm hơn.
4. **Không gắn cùng goal hai lần** khi packaging đã bind mặc định nếu không có nhu cầu rõ: ví dụ tự thêm execution `compiler:compile` có thể gây biên dịch lặp, còn `jar:jar` có thể dẫn đến tạo JAR chính trùng.
5. **Dùng execution configuration riêng** khi mỗi lượt cần tham số khác.
6. **Ưu tiên một plugin declaration với nhiều execution**, không duplicate plugin entries.
7. **Đặt `<phase>` tường minh** nếu default phase không rõ; đọc docs khi bỏ phase.
8. **Giữ thứ tự POM có chủ ý** nếu nhiều execution cùng phase có phụ thuộc logic.
9. **Kiểm tra parent/profile** trước khi thêm ID để tránh merge ngoài ý muốn.
10. **Phân biệt lifecycle goal với direct CLI goal**: `package` khác `plugin:goal`.
11. **Test tối thiểu hai phase đích khác nhau**: một phase trước execution và một phase sau nó để chứng minh binding đúng.
12. **Đọc log và Effective POM**, vì XML hợp lệ không chứng minh goal đã chạy.

## 17. Bài tập tự kiểm tra

1. Vì sao `<execution><id>announce-initialize</id>` **không đủ** để quyết định plugin chạy ở phase nào?
2. Trong POM bài học, `mvn validate` chạy bao nhiêu execution AntRun? Vì sao?
3. `mvn test` có chạy `announce-prepare-a` không? Vì sao?
4. `mvn package` chạy những execution AntRun nào và theo thứ tự nào?
5. Tại sao `mvn clean package` **không** có nghĩa `clean` thuộc default lifecycle?
6. Khi `<goals>` có `tree` và `analyze-only`, đó là goal của plugin nào? Vì sao không thể đặt hai goal này vào AntRun Plugin?
7. Có thể dùng cùng ID `shared-check` ở parent và child để làm gì? Khác gì dùng hai ID riêng?
8. Tại sao `<pluginManagement>` không đồng nghĩa một execution AntRun được chạy ở mọi module?
9. Khi gọi `mvn antrun:run`, Maven có nhất thiết chạy các execution `initialize` và `prepare-package` không?
10. Goal không khai báo phase có thể tự chạy trong lifecycle trong trường hợp nào?
11. Vì sao nên kiểm tra `help:effective-pom` bên cạnh việc đọc POM nguồn?
12. Nếu goal sinh code chạy sau `compile`, điều gì có thể xảy ra và nên đặt nó vào phase nào?

**Tóm tắt:** Một `<execution>` định nghĩa **một lần gắn plugin goal vào build**, nhận diện bằng `<id>`, chọn lúc chạy bằng `<phase>` (hoặc default phase của goal khi phù hợp) và chọn việc cần làm bằng `<goals>`. Có thể có **nhiều execution cùng plugin**, nhiều goal trong một execution, và cấu hình riêng cho từng execution. Maven chạy các phase theo thứ tự lifecycle; execution trùng phase thường theo thứ tự khai báo và chịu ảnh hưởng của packaging, parent và profile. Để xác minh, dùng **`mvn <phase>`, build log, `help:effective-pom`** và tài liệu của đúng plugin.

## Tài liệu tham khảo chính thức

- [Apache Maven — Guide to Configuring Plug-ins (executions, id, phase, goals, inheritance)](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Introduction to the Build Lifecycle (phase, goals, ordering)](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven AntRun Plugin 3.2.0 — antrun:run](https://maven.apache.org/components/plugins-archives/maven-antrun-plugin-3.2.0/run-mojo.html)
- [Apache Maven AntRun Plugin — Usage](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html)
- [Apache Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
