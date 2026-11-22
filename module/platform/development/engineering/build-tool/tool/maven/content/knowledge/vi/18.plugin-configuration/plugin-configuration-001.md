# build/plugins và build/pluginManagement: vai trò và cách áp dụng

## 1. Câu hỏi cốt lõi: khai báo plugin để chạy hay quản lý cấu hình dùng chung?

Trong Maven, phần lớn công việc của một build — copy resources, compile Java, chạy test, tạo JAR, kiểm tra code, đóng gói và deploy — đều được thực hiện bằng **plugin goals**. Một file `pom.xml` có hai vị trí quan trọng, dễ nhầm lẫn:

- **`<build><plugins>`**: khai báo các build plugin **được sử dụng trong project**, cùng cấu hình và các `<executions>` nếu có. Execution được bind vào lifecycle có thể thực thi khi Maven đi đến phase tương ứng.
- **`<build><pluginManagement><plugins>`**: cung cấp **version, cấu hình, dependencies và executions mặc định/được quản lý** cho plugin *khi plugin ấy được sử dụng*. Đặt một plugin tùy ý trong `pluginManagement` **không tự kích hoạt goal của nó**.

Phân biệt này đặc biệt quan trọng khi project có **parent POM** hoặc reactor nhiều module. Một công ty có thể quản lý version và policy của Compiler, Surefire, Checkstyle, JaCoCo, Shade... ở parent, trong khi từng module quyết định plugin nào cần thực sự áp dụng.

**Quy tắc ngắn gọn:**

> `pluginManagement` nói “**nếu dùng plugin này thì dùng version/cấu hình/execution nào**”; `plugins` nói “**project này sử dụng plugin này**”. Ngoài ra, packaging có thể tạo **lifecycle bindings mặc định**, nên plugin như Compiler/Jar/Surefire vẫn có thể chạy mà không cần được viết tường minh trong `build/plugins`.

Ngoại lệ lifecycle mặc định này rất quan trọng: không nên nói “không có dòng trong `<plugins>` thì tuyệt đối không chạy plugin”. Với packaging `jar`, Maven vốn đã bind một số plugin goals để compile, test và package.

### Sau bài này bạn sẽ làm được gì?

1. Xác định đúng vị trí của `build/plugins` và `build/pluginManagement`.
2. Giải thích **plugin, goal, execution, phase và packaging lifecycle binding**.
3. Quản lý versions và tham số build chung tại parent POM mà không vô tình kích hoạt plugin ở mọi module.
4. Áp dụng một plugin được quản lý bằng khai báo tối giản trong child.
5. Biết khi nào Maven vẫn chạy compiler dù compiler chỉ hiện diện dưới `pluginManagement`.
6. Tránh chạy lặp goal, cấu hình sai execution ID hoặc nhầm plugin dependencies với project dependencies.
7. Dùng `help:effective-pom` và build log để xác minh plugin version/configuration/execution thực tế.

## 2. Cấu trúc POM chính xác

Hai khối là **anh em trong phần `<build>`**, không phải hai cách viết tương đương:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <!-- ... các thông tin project ... -->

    <build>
        <!-- Những build plugins mà project khai sử dụng -->
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>

        <!-- Những phiên bản và cấu hình được quản lý -->
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.2.5</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Đây là một **đoạn POM minh họa**: có dấu chú thích thay cho các thành phần bắt buộc như `modelVersion/groupId/artifactId/version`, nên chưa phải project độc lập. Cấu trúc lồng nhau mới là trọng tâm.

Với cả hai vị trí, `<plugin>` thường nhận các trường:

| Trường | Chức năng |
| --- | --- |
| `<groupId>` | Group của plugin; với plugin chính thức thường là `org.apache.maven.plugins` |
| `<artifactId>` | Tên artifact plugin như `maven-compiler-plugin` |
| `<version>` | Phiên bản plugin, nên pin để build tái lập |
| `<configuration>` | Cấu hình dùng chung ở **plugin level**; tham số phải đúng goal/plugin đó hỗ trợ |
| `<executions>` | Một hoặc nhiều execution, có `id`/`phase`/`goals`/`configuration` |
| `<dependencies>` | Dependency **của chính plugin**, tách với project dependency |
| `<inherited>` | Điều khiển việc truyền cấu hình plugin từ parent sang child trong ngữ cảnh phù hợp |
| `<extensions>` | Cho phép plugin đóng vai trò build extension nếu cần; không dùng tùy tiện |

Nên khai `groupId` và `version` tường minh để người khác đọc dễ hiểu, dù Maven có quy tắc mặc định đối với một số plugin chính thức.

## 3. So sánh `plugins` và `pluginManagement`

| Tiêu chí | `build/plugins` | `build/pluginManagement` |
| --- | --- | --- |
| Mục đích | Khai báo plugin sử dụng cho project | Quản lý version/configuration/executions khi plugin được sử dụng |
| Tự tạo một plugin execution bất kỳ? | Có thể, khi execution được bind hợp lệ | **Không**, chỉ đứng trong management chưa đủ |
| Có thể chứa `<version>`? | Có | Có, thường dùng để pin version ở parent |
| Có thể chứa `<configuration>`? | Có | Có, như cấu hình mặc định áp dụng khi plugin hoạt động |
| Có thể chứa `<executions>`? | Có | Có, nhưng execution được quản lý chỉ có hiệu lực khi plugin được kích hoạt |
| Hay đặt ở đâu? | POM project hoặc parent khi muốn áp dụng cho các child | Parent POM hoặc POM hiện tại để tập trung policy |
| Child có thể override? | Có, theo merge/inheritance rules | Có, bằng plugin declaration/configuration cụ thể |
| Có thể cùng tồn tại? | Có | Có, và Maven hợp nhất thông tin khi plugin được sử dụng |

**Tình huống ứng dụng:** parent quản lý `maven-antrun-plugin`, execution `validate` để in thông điệp. Chỉ module cần bước ấy mới khai `maven-antrun-plugin` dưới `build/plugins`; các module không khai plugin sẽ không tự chạy execution này.

Nhưng với `maven-compiler-plugin` trong project `jar`, packaging đã cung cấp lifecycle binding `compiler:compile`. Cấu hình/version trong `pluginManagement` **vẫn có thể áp dụng cho plugin được gọi từ binding mặc định**. Điều đó không mâu thuẫn với nguyên tắc management không tự thêm **execution tùy ý**.

## 4. Hiểu plugin → goal → execution → phase

Maven có khái niệm **lifecycle phase** như `validate`, `compile`, `test`, `package` và `verify`. Plugin cung cấp **goals**. Một `execution` chỉ cách và thời điểm chạy goal.

Ví dụ:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <executions>
        <execution>
            <id>print-build-banner</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Build configuration activated"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Đây là **đoạn plugin** cần đặt dưới `build/plugins` (hoặc `build/pluginManagement/plugins` nếu chỉ muốn quản lý). Đọc nó như sau:

- Plugin `maven-antrun-plugin` cung cấp goal `run`.
- `<id>print-build-banner</id>` định danh execution để Maven merge/override khi có parent và profiles.
- `<phase>validate</phase>` liên kết execution với phase `validate`.
- `<goals><goal>run</goal>` chọn goal thực hiện.
- `<configuration><target><echo .../></target>` là cấu hình AntRun goal.
- Nếu execution ở **`build/plugins`**, `mvn validate` sẽ đi đến phase `validate` và có thể chạy goal đó.
- Nếu **chỉ** có execution này ở `pluginManagement` và chưa có một cơ chế nào sử dụng plugin, `mvn validate` **không tự kích hoạt** AntRun.

### Chỉ thêm plugin vào `build/plugins` chưa chắc đã có hành vi mới

Một plugin có thể không được bind sẵn vào lifecycle; nếu chỉ viết:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
</plugin>
```

thì chưa có execution/phase/goal cụ thể để Maven biết AntRun cần chạy khi nào. Việc khai trong `build/plugins` là **điều kiện cấu hình/sử dụng plugin**, nhưng với những goal không có lifecycle binding thích hợp, bạn vẫn cần `<executions>` hoặc gọi goal trực tiếp.

Ngược lại, plugin `maven-compiler-plugin` đã được packaging `jar` bind ở `compile` và `test-compile`. Chỉ thêm một execution `compiler:compile` tùy ý mà không xét default binding có thể khiến compile chạy **hai lần**.

### Cấu hình plugin level so với execution level

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <configuration>
        <!-- tham số dùng chung cho plugin khi phù hợp -->
    </configuration>
    <executions>
        <execution>
            <id>custom-validate</id>
            <phase>validate</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="Execution-specific configuration"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
```

`<configuration>` **trực tiếp dưới plugin** cung cấp cấu hình chung; `<configuration>` **bên trong execution** chuyên biệt cho execution đó. Cấu hình hiệu lực được merge theo model/plugin rules, không chỉ đơn giản thay nguyên toàn bộ block bất kể tham số.

## 5. Binding mặc định từ `packaging`: nguyên nhân nhiều người hiểu sai

Maven không cần bạn viết từng plugin trong POM để một build `jar` cơ bản hoạt động. Packaging cung cấp **default lifecycle bindings**:

| Phase | Goal thường được bind khi packaging `jar` |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |
| `install` | `install:install` |
| `deploy` | `deploy:deploy` |

Vì vậy nếu `pom.xml` có `<packaging>jar</packaging>`, `mvn package` sẽ thực hiện các phase trước `package` cùng những goals tương ứng, dù POM không khai compiler, resources, surefire hoặc jar plugin ở `build/plugins`.

**Cách dùng chuẩn:** parent có thể pin:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</pluginManagement>
```

Khi child `jar` chạy lifecycle, compiler và jar plugins có thể lấy version/cấu hình từ plugin management. **Management không tự tạo một lifecycle khác**; nó điều chỉnh plugin đã được packaging dùng.

Ngược lại, với packaging `pom`, lifecycle mặc định không bind các goal compile/JAR như project `jar`. Root aggregator/parent POM thường dùng packaging `pom` và có thể chỉ quản lý các plugin, trong khi child `jar` thực hiện compile/package.

**Không lẫn lộn:** `<dependencyManagement>` quản lý version/scope **project dependencies**; `<pluginManagement>` quản lý **build plugins**. Import BOM qua `scope=import` không mang plugin management của BOM vào project.

## 6. Thực hành Java 17: parent quản lý, một child kích hoạt, một child không

Đây là ví dụ có thể tạo đầy đủ trên máy có **JDK 17+ và Maven 3.6.3+**, không dùng dependency Java bên ngoài. Lần đầu chạy Maven có thể cần tải các plugins từ repository/mirror.

### 6.1. Cấu trúc

```text
plugin-lab/
├── pom.xml
├── passive-app/
│   ├── pom.xml
│   └── src/main/java/dev/training/passive/Main.java
└── active-app/
    ├── pom.xml
    └── src/main/java/dev/training/active/Main.java
```

Mục tiêu:

- Root POM vừa là **parent** vừa là **aggregator**, khai `<modules>` và `<pluginManagement>`.
- Cả hai child đều là `jar`, sử dụng managed compiler plugin version/configuration do lifecycle mặc định.
- Chỉ `active-app` khai `maven-antrun-plugin` tại `<build><plugins>`.
- Root **chỉ quản lý** AntRun execution trong `pluginManagement`, không có AntRun ở `build/plugins`.
- Kết quả: khi chạy `validate`, chỉ `active-app` có log echo của AntRun; các ứng dụng Java vẫn có thể compile và chạy.

### 6.2. Root POM — `plugin-lab/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.training</groupId>
    <artifactId>plugin-lab</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>passive-app</module>
        <module>active-app</module>
    </modules>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>

                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>

                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-antrun-plugin</artifactId>
                    <version>3.1.0</version>
                    <executions>
                        <execution>
                            <id>managed-validate-banner</id>
                            <phase>validate</phase>
                            <goals>
                                <goal>run</goal>
                            </goals>
                            <configuration>
                                <target>
                                    <echo message="MANAGED_BANNER: active-app"/>
                                </target>
                            </configuration>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
```

Những điểm phải chú ý:

1. Parent dùng `<packaging>pom</packaging>` vì nó quản lý build của nhiều child; nó không tự tạo JAR cho source Java.
2. `<pluginManagement>` **không nằm dưới `<plugins>`** mà trực tiếp dưới `<build>`.
3. Compiler và Jar Plugin có phiên bản pin trong management; các default lifecycle bindings của `jar` có thể nhận cấu hình này.
4. AntRun goal `run` có execution `managed-validate-banner` ở phase `validate`, nhưng **vẫn chỉ là managed execution**.
5. Thông điệp `MANAGED_BANNER: active-app` là text cố định trong config: nếu module khác kích hoạt AntRun cùng managed execution, nó cũng sẽ in nội dung ấy. Ở bài thực hành, chỉ `active-app` kích hoạt.

### 6.3. Child không kích hoạt AntRun — `passive-app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training</groupId>
        <artifactId>plugin-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>passive-app</artifactId>
    <packaging>jar</packaging>
</project>
```

Child **không có `<build><plugins>`** và không khai AntRun. Nhưng nó vẫn có compiler/JAR lifecycle vì packaging `jar` và nhận được management của parent.

File `passive-app/src/main/java/dev/training/passive/Main.java`:

```java
package dev.training.passive;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Passive app ready");
    }
}
```

### 6.4. Child kích hoạt AntRun — `active-app/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.training</groupId>
        <artifactId>plugin-lab</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>active-app</artifactId>
    <packaging>jar</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Lưu ý **không khai `<version>`, `<executions>` hoặc `<configuration>` ở AntRun trong child**. Maven lấy các giá trị này từ `pluginManagement` đã kế thừa từ parent. Điều này minh họa đúng vai trò “managed defaults”.

File `active-app/src/main/java/dev/training/active/Main.java`:

```java
package dev.training.active;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Active app ready");
    }
}
```

### 6.5. Chạy Maven theo phase

Từ thư mục `plugin-lab/`, chạy:

```bash
mvn -version
mvn -B -ntp clean verify
```

Khi Maven vào phase `validate`:

- Root `plugin-lab` có packaging `pom` và chỉ quản lý AntRun, nên không tự in managed banner.
- `passive-app` không kích hoạt AntRun, nên không có execution AntRun do project yêu cầu.
- `active-app` khai AntRun trong `build/plugins`, nên managed execution ở `validate` được áp dụng.

Trong log build của `active-app`, bạn **kỳ vọng thấy thông điệp có nội dung**:

```text
MANAGED_BANNER: active-app
```

Đây là **chuỗi nội dung do Ant `echo` in vào log**, không phải stdout toàn bộ của Maven: terminal còn có các dòng plugin header, `[INFO]`, tên module và trạng thái build; cách prefix log có thể khác theo Maven/AntRun version.

Maven cũng chạy các goal mặc định của packaging `jar` như compiler và jar packaging để tạo:

```text
passive-app/target/passive-app-1.0.0.jar
active-app/target/active-app-1.0.0.jar
```

### 6.6. Chạy Java để xác nhận project biên dịch được

**Bash/Linux/macOS**, đứng tại `plugin-lab/`:

```bash
java -cp passive-app/target/passive-app-1.0.0.jar dev.training.passive.Main
java -cp active-app/target/active-app-1.0.0.jar dev.training.active.Main
```

**Stdout chính xác từ hai chương trình Java theo thứ tự hai lệnh:**

```text
Passive app ready
Active app ready
```

**Windows PowerShell**:

```powershell
java -cp passive-app\target\passive-app-1.0.0.jar dev.training.passive.Main
java -cp active-app\target\active-app-1.0.0.jar dev.training.active.Main
```

Hai project chưa cấu hình `Main-Class` trong manifest; `java -cp ... <fully-qualified-class>` là cách phù hợp. Không mặc định dùng `java -jar` với hai JAR này.

### 6.7. Thử nghiệm tách riêng để thấy sự khác biệt

Từ `plugin-lab/`:

```bash
mvn -B -ntp -pl passive-app validate
mvn -B -ntp -pl active-app validate
```

- Lệnh đầu **không** nên có `MANAGED_BANNER: active-app` do AntRun, vì `passive-app` chưa khai AntRun trong `plugins`.
- Lệnh thứ hai **nên có** thông điệp đó, do `active-app` đã kích hoạt AntRun.

Nếu không thấy banner ở `active-app`, trước tiên kiểm tra `help:effective-pom` và error logs: parent có resolve đúng không, plugin có cấu hình execution `managed-validate-banner` không, POM child có thật sự khai AntRun không, Maven có chạy đến phase `validate` không.

## 7. Vì sao `pluginManagement` có thể xuất hiện trong effective POM nhưng không chạy?

Chạy từ `plugin-lab/`:

```bash
mvn -f passive-app/pom.xml help:effective-pom
mvn -f active-app/pom.xml help:effective-pom
```

So sánh:

- **Passive child:** effective POM có thể hiển thị `pluginManagement` của parent, trong đó có AntRun configuration. Việc quản lý hiện diện **không đồng nghĩa AntRun sẽ chạy** trong lifecycle.
- **Active child:** effective POM có phần plugin AntRun đang được sử dụng và các cấu hình/executions được quản lý đã hợp nhất; Maven có execution liên kết với `validate`.
- **Cả hai:** được kế thừa `maven.compiler.release=17` và quản lý phiên bản compiler/jar plugins; lifecycle của packaging `jar` vẫn hoạt động.

Bạn có thể tạo effective POM vào file để xem dễ hơn (đặt file ngoài thư mục cần commit nếu phù hợp):

```bash
mvn -f passive-app/pom.xml help:effective-pom -Doutput=passive-effective-pom.xml
mvn -f active-app/pom.xml help:effective-pom -Doutput=active-effective-pom.xml
```

Đường dẫn `-Doutput` được plugin xử lý theo môi trường/working directory đang gọi; không nên giả định file sẽ xuất hiện trong một thư mục nhất định khi chạy từ script khác. Với phiên bản Help Plugin hỗ trợ, `-Dverbose` có thể bổ sung chỉ dẫn nguồn cho các phần trong effective POM:

```bash
mvn -f active-app/pom.xml help:effective-pom -Dverbose
```

Khi kiểm tra, tìm `maven-antrun-plugin`, `managed-validate-banner`, `maven-compiler-plugin` và các phiên bản `3.1.0` / `3.13.0`.

**Quan trọng:** effective POM là **model cấu hình hiệu lực**; nó không phải bản log “plugin đã chạy ở thời điểm này”. Muốn biết execution thực sự chạy, cần xem build log, output và kết quả test/packaging.

## 8. Parent POM và inheritance: cách quản lý một lần cho nhiều module

Trong tổ chức có nhiều module, parent POM thường đặt phiên bản plugin ở `pluginManagement`:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Nếu các child có packaging `jar`, Maven gọi compiler/surefire theo default lifecycle. Parent-management giúp dùng cùng phiên bản và cấu hình được chọn, ngay cả khi child không viết plugin tường minh. Với plugin **không thuộc default binding**, child chủ động khai trong `build/plugins` để nhận cấu hình được quản lý.

### Parent có `build/plugins` thì sao?

Nếu parent POM khai một plugin có executions trực tiếp dưới `build/plugins`, cấu hình đó **thường được kế thừa xuống child** (trừ khi có `<inherited>false</inherited>` hoặc quy tắc inheritance khác).

Ví dụ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <executions>
                <execution>
                    <id>parent-always-run</id>
                    <phase>validate</phase>
                    <goals>
                        <goal>run</goal>
                    </goals>
                    <configuration>
                        <target>
                            <echo message="Parent build policy is active"/>
                        </target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
```

Đây là **đoạn POM minh họa thay thế**, không thêm nguyên xi vào ví dụ thực hành vì sẽ thay đổi kết quả so sánh. Nếu đặt ở `build/plugins` của parent mà không hạn chế inheritance, execution có thể chạy trong cả hai child khi chúng đạt phase `validate`. Khác với quản lý ở `pluginManagement`, cách này **mang tính áp đặt** hơn.

### `<inherited>false</inherited>` dùng khi nào?

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <inherited>false</inherited>
    <!-- phần cấu hình cần dùng riêng ở parent -->
</plugin>
```

Đoạn trên minh họa tùy chọn điều khiển inheritance ở **plugin level**; `<inherited>false</inherited>` có thể dùng để tránh truyền cấu hình plugin từ parent xuống child. Một `<execution>` cũng có tùy chọn `<inherited>` trong mô hình plugin execution.

Đừng dùng tùy chọn này như biện pháp chữa mọi lỗi plugin chạy nhầm: cần phân biệt thực sự muốn plugin ở parent, chỉ muốn quản lý version, hay chỉ muốn kích hoạt ở một số child.

### Aggregator khác parent

Root `plugin-lab/pom.xml` có cả `<modules>` và được child dùng làm `<parent>`:

- `<modules>` quyết định các module được đưa vào **reactor** khi chạy build từ root.
- `<parent>` quyết định **inheritance của POM**.
- `<pluginManagement>` không tự tạo dependency reactor hoặc quyết định thứ tự build.

Một module có thể tham gia aggregator mà kế thừa parent khác. Một project cũng có thể dùng parent POM đã publish ở remote repository mà không tham gia reactor nào cùng parent đó.

## 9. Khi child override cấu hình được quản lý

`pluginManagement` là **cấu hình mặc định để dùng lại**, không phải luật bất biến. Child có thể thêm hoặc override các trường.

Giả sử parent quản lý Compiler Plugin:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
            </configuration>
        </plugin>
    </plugins>
</pluginManagement>
```

Nếu child có yêu cầu Java 21 và môi trường thực sự cấp JDK/toolchain tương ứng, child có thể chủ động cấu hình:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <configuration>
                <release>21</release>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Đây chỉ là **đoạn minh họa**, không dùng với ví dụ JDK 17 đang chạy ở trên. Maven có thể nhận **version plugin `3.13.0` từ parent management**, còn tham số `release` tại child ghi đè giá trị được quản lý phù hợp.

**Lưu ý:** `<release>21</release>` không có nghĩa JDK 17 bỗng có thể tạo bytecode Java 21. Nếu không dùng toolchain/JDK phù hợp, build sẽ lỗi kiểu “release version 21 not supported”.

### Merge configuration phức tạp

Maven có các quy tắc hợp nhất DOM configuration giữa parent/child hoặc management/usage. Với phần tử XML lồng nhau, các thuộc tính như `combine.self="override"` và `combine.children="append"` đôi khi được sử dụng để điều khiển cách merge thay vì suy đoán rằng toàn bộ config được replace.

Ví dụ minh họa một phần configuration được override:

```xml
<configuration combine.self="override">
    <release>17</release>
</configuration>
```

Đoạn này phải đặt trong đúng cấu trúc plugin, không phải POM độc lập. Không nên sử dụng các chỉ thị combine một cách tùy tiện; đọc **effective POM** và kiểm tra plugin behavior sau khi đổi.

## 10. Execution ID: cùng tên có thể merge, khác tên tạo execution khác

Một plugin có thể có nhiều executions:

```xml
<executions>
    <execution>
        <id>quality-main</id>
        <phase>verify</phase>
        <goals>
            <goal>check</goal>
        </goals>
    </execution>
</executions>
```

Đây là đoạn minh họa **chỉ hợp lệ khi plugin cụ thể có goal `check`**, không phải execution runnable độc lập.

Trong inheritance:

- Execution **cùng `id`** trong parent và child được hợp nhất/child có thể override các thành phần phù hợp, tùy cấu trúc và merge rules.
- Execution có **`id` khác nhau** thường vẫn tồn tại riêng, nên có thể khiến **hai goals cùng chạy** nếu chúng cùng bind vào một phase.
- Nếu không khai `id`, Maven có cơ chế ID mặc định; khi cần override có chủ đích, hãy khai ID rõ ràng.

Ví dụ parent quản lý:

```xml
<execution>
    <id>managed-validate-banner</id>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <configuration>
        <target><echo message="Parent banner"/></target>
    </configuration>
</execution>
```

Child kích hoạt plugin và muốn đổi thông điệp của **chính execution này** có thể khai **cùng ID**:

```xml
<execution>
    <id>managed-validate-banner</id>
    <configuration>
        <target><echo message="Child banner"/></target>
    </configuration>
</execution>
```

Hai đoạn là ví dụ về **thành phần trong executions của cùng một plugin**, không dùng độc lập. Maven hợp nhất theo ID, giữ/bổ sung các trường không bị override theo effective configuration. Hãy xem `help:effective-pom` để xác nhận phase/goal thực tế, vì details có thể phụ thuộc merge và những cấu hình khác.

### Chú ý `default-compile`, `default-testCompile` và `default-cli`

Một số execution đến từ lifecycle bindings mặc định, có ID như `default-compile` hoặc `default-testCompile`. Khi cần điều chỉnh riêng execution mặc định, có thể có cách khai cùng ID trong cấu hình plugin. Direct CLI goal invocation cũng có cơ chế execution ID riêng như `default-cli` hoặc cú pháp `plugin:goal@executionId` trong Maven tương thích.

**Không nên** tự thêm một execution `compiler:compile` mới với ID khác vào `compile` khi mặc định packaging `jar` đã có compiler goal. Việc đó có thể khiến Maven compile hai lần; hãy điều chỉnh configuration/ID của execution đã có hoặc plugin-level configuration cho nhu cầu đơn giản.

## 11. Hai kiểu cấu hình thường gặp trong thực tế

### Kiểu A — quản lý version ở parent, kích hoạt khi cần

Parent:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>example-task</id>
                        <phase>validate</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target><echo message="Task from parent"/></target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Child **cần** task:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
        </plugin>
    </plugins>
</build>
```

Child **không cần** thì không thêm plugin ấy. Đây là thiết kế phù hợp khi chỉ một số module chạy code generation, special packaging, static analysis hoặc deploy-specific task.

### Kiểu B — áp dụng plugin/execution cho mọi child qua parent

Đặt plugin thực sự dưới `build/plugins` của parent (với inheritance mặc định). Dùng khi policy cần chạy nhất quán tại mọi module: ví dụ license check, code quality hoặc verification. Tuy nhiên, nhớ đánh giá packaging `pom` của parent, vì chính root cũng có thể chạy execution đã bind nếu không được giới hạn hợp lý.

**Chọn kiểu B có chủ đích**; nếu một plugin không áp dụng cho tất cả module, thường nên quản lý ở `pluginManagement` rồi cho module cần thiết khai `plugins`.

### Kiểu C — dùng plugin mặc định của lifecycle, quản lý version ở parent

Các plugin như Compiler, Resources, Surefire và Jar được gọi thông qua lifecycle của `jar`. Một `pluginManagement` ở parent có thể pin version và cấu hình chung mà child không phải khai lại:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration><release>17</release></configuration>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.2.5</version>
        </plugin>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-jar-plugin</artifactId>
            <version>3.4.2</version>
        </plugin>
    </plugins>
</pluginManagement>
```

Điều này **không** chứng minh mọi loại test tự động có execution phù hợp: nếu bạn dùng Maven Failsafe cho integration tests, các executions `integration-test`/`verify` vẫn cần cấu hình riêng khi muốn thực sự chạy.

## 12. Vì sao không được nhầm với dependency management hoặc plugin dependencies?

Một project có hai classpath chính cần phân biệt:

1. **Project dependencies**: những thư viện mà ứng dụng dùng để compile/test/run.
2. **Plugin dependencies**: các thư viện mà Maven plugin cần để thực hiện goal của chính plugin.

Ví dụ, khai một project dependency:

```xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.14.0</version>
    </dependency>
</dependencies>
```

Không làm Compiler Plugin tự đổi phiên bản.

Ngược lại, dependency nằm **bên trong plugin**:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <dependencies>
        <!-- plugin-specific dependencies, nếu có nhu cầu hợp lệ -->
    </dependencies>
</plugin>
```

không tương đương việc thêm dependency ấy vào classpath của mã ứng dụng. Đoạn trên là minh họa cấu trúc, không phải cấu hình plugin dependency hoàn chỉnh.

Cơ chế **`<dependencyManagement>` của project không bảo đảm quản lý transitive dependencies của plugin**. Nếu lỗi thuộc plugin classpath, hãy kiểm tra plugin version, plugin dependency declarations, Maven/plugin compatibility và plugin repository.

## 13. Phân biệt trực tiếp gọi plugin goal với chạy lifecycle

Hai command:

```bash
mvn clean verify
mvn org.apache.maven.plugins:maven-antrun-plugin:3.1.0:run
```

không cùng nghĩa:

- `mvn clean verify` chạy lifecycle phases cho tới verify (và clean lifecycle), bao gồm các goals được bind bởi packaging và POM executions.
- Lệnh thứ hai **gọi trực tiếp một goal** của AntRun Plugin. Nó không mặc nhiên chạy tất cả phases trước verify. Goal có thể cần configuration phù hợp; khi gọi trực tiếp, execution/configuration được chọn còn tùy cách bạn khai và cách Maven xử lý `default-cli` hoặc execution ID.
- Muốn chạy một execution cụ thể đã cấu hình, Maven hỗ trợ cú pháp `plugin:goal@executionId` trong các phiên bản tương thích, nhưng cần hiểu plugin configuration thực tế.

Ví dụ:

```bash
mvn -f active-app/pom.xml validate
mvn -f active-app/pom.xml help:effective-pom
```

Command `validate` ở ví dụ làm AntRun execution được bind chạy; `help:effective-pom` chỉ **hiển thị mô hình**, không tương đương thực thi các goals build.

### Plugin prefix và version

`mvn compiler:compile` dùng prefix resolution; nếu muốn cố định chính xác plugin:

```bash
mvn org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile
```

Cách gọi đầy đủ giúp bỏ qua mơ hồ prefix/phiên bản, nhưng **vẫn không tự chạy tất cả lifecycle prerequisite**. Vì vậy thông thường hãy chọn phase `mvn compile`/`mvn test`/`mvn verify` để Maven thực hiện thứ tự build đúng; chỉ gọi goal trực tiếp khi biết lý do.

## 14. Kiểm tra plugin đang dùng version nào

Các lệnh hữu ích:

```bash
mvn help:effective-pom
mvn help:effective-pom -Dverbose
mvn help:active-profiles
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
```

- **Effective POM**: kiểm tra thông tin kế thừa/merge của `build/plugins` và `pluginManagement`; xem version và executions hiệu lực.
- **Verbose effective POM**: ở plugin version hỗ trợ, các chú thích có thể giúp truy nguồn cấu hình từ parent/profile/POM.
- **Active profiles**: profile có thể thêm plugin hoặc thay đổi cấu hình.
- **`help:describe`**: xem goal/parameters của plugin; rất hữu ích khi không rõ tên tham số trong `configuration`.

Với bài thực hành, nên so sánh hai child bằng:

```bash
mvn -f passive-app/pom.xml help:effective-pom
mvn -f active-app/pom.xml help:effective-pom
mvn -B -ntp -pl passive-app validate
mvn -B -ntp -pl active-app validate
```

Nếu một execution có vẻ không chạy, hãy kiểm tra xem nó:

1. Chỉ tồn tại dưới `pluginManagement` hay đã có plugin được kích hoạt?
2. Có `<goals>` không, và goal đó có thật sự thuộc plugin?
3. Có `<phase>` phù hợp hoặc goal có default phase binding không?
4. Build đã chạy đến phase đó chưa?
5. `<inherited>false</inherited>` hoặc profile có ngăn/đổi cấu hình không?
6. Có bị merge/override bằng execution `id` cùng tên không?
7. Có đang xem đúng module và POM thực tế không?

Khi cần, dùng `mvn -e` để có stacktrace hoặc `mvn -X` để debug plugin resolution/execution. Không đăng nguyên debug logs chứa đường dẫn, private repository URL hay secrets lên nơi công khai.

## 15. Lỗi phổ biến và hướng xử lý

| Triệu chứng | Nguyên nhân hay gặp | Cách xử lý |
| --- | --- | --- |
| Khai plugin trong `pluginManagement` nhưng không chạy | Chỉ quản lý, chưa có plugin usage/binding | Thêm plugin vào `build/plugins` khi cần; với goal tự chọn, cấu hình execution |
| Module bất ngờ chạy plugin | Parent khai plugin/execution trong `build/plugins` và kế thừa | Kiểm tra parent, `inherited`, effective POM và profiles |
| Maven Compiler vẫn chạy dù child không có `plugins` | Default lifecycle binding của packaging `jar` | Đây là hành vi đúng; dùng pluginManagement để quản lý version/config |
| Plugin sai version | Không pin version, parent override, profile hoặc effective management khác kỳ vọng | Kiểm tra effective POM và pin plugin version có chủ đích |
| `No plugin found for prefix` | Prefix/pluginGroups/pluginRepositories hoặc metadata resolution | Kiểm tra plugin repo/settings; thử tọa độ plugin đầy đủ |
| `PluginResolutionException` | Plugin artifact/dependencies không resolve được | Kiểm tra `pluginRepositories`, mirror, quyền và network |
| Plugin thực thi hai lần | Goal đã có default lifecycle binding, lại thêm custom execution hoặc IDs khác nhau | Kiểm tra các executions và lifecycle mapping |
| Child không override đúng | Config merge, execution ID không khớp hoặc parent inheritance | Dùng đúng `id`, xem effective POM và `combine.*` nếu cần |
| Chỉnh `dependencyManagement` mà plugin không thay | Hai cơ chế khác nhau | Đổi `pluginManagement`/`build/plugins` |
| Module chỉ dùng Maven 17? | Nhầm version của JDK, compiler target và Maven | Kiểm tra `mvn -version`, `java -version`, `release`/toolchains |
| Plugin chạy khi bạn gọi goal trực tiếp nhưng không chạy khi `verify` | Chưa bind goal vào phase hoặc chưa kích hoạt plugin | Tạo execution với `phase/goals` phù hợp |
| Plugin configuration không có tác dụng | Tham số đặt sai level hoặc không được goal hỗ trợ | Xem `help:describe`/plugin docs và effective POM |

**Không nên “chữa” một plugin không chạy bằng cách copy toàn bộ `pluginManagement` vào `plugins` trong tất cả modules.** Điều đó dễ tạo duplicate executions, thay đổi lifecycle không mong muốn và tăng chi phí bảo trì. Xác định module nào cần chạy plugin trước.

## 16. Cách thiết kế một parent POM có trách nhiệm

Một parent POM ổn định thường nên:

1. **Pin version của plugins** trong `pluginManagement` để CI/laptop không phụ thuộc version Maven tự chọn. Ưu tiên phiên bản plugin được tổ chức kiểm thử.
2. **Quản lý Java release/encoding** và những tham số không có sự khác biệt giữa modules.
3. Đặt plugin tùy chọn trong `pluginManagement`, để child khai `build/plugins` khi cần.
4. Đặt policy bắt buộc cho mọi child trong `build/plugins` có chủ đích, và hiểu tác dụng của inheritance.
5. Không gắn mục tiêu tùy chọn vào phase quá sớm nếu nó gây build chậm hoặc fail trên module không cần.
6. Giữ **execution IDs có tên rõ**, để child override có kiểm soát.
7. Không khai trùng cùng một plugin nhiều lần trong một danh sách `build/plugins`; Maven 3 có thể cảnh báo và Maven 4 có thể coi đây là lỗi.
8. Chạy `help:effective-pom` và build smoke tests trên cả module dùng và không dùng plugin khi nâng parent.
9. Tách dependency version policy (`dependencyManagement`/BOM) khỏi plugin version policy (`pluginManagement`) khi các nhóm có vòng đời nâng cấp khác nhau.
10. Tài liệu hóa những plugin thực sự chạy ở mỗi lifecycle phase và những plugin chỉ được quản lý.

**Về bảo mật:** một plugin được kích hoạt trong CI có thể chạy code và truy cập filesystem/network theo quyền của runner. Không thêm plugin lạ vào `build/plugins` chỉ để tránh một warning; thẩm định nguồn plugin và version, giới hạn quyền CI và không cấp secrets cho job không đáng tin cậy.

## 17. Bài tập tự kiểm tra

**Bài 1:** Parent chỉ có:

```xml
<pluginManagement>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
            <version>3.1.0</version>
            <executions>
                <execution>
                    <id>x</id>
                    <phase>validate</phase>
                    <goals><goal>run</goal></goals>
                    <configuration>
                        <target><echo message="HELLO"/></target>
                    </configuration>
                </execution>
            </executions>
        </plugin>
    </plugins>
</pluginManagement>
```

Child `jar` không có AntRun trong `build/plugins`. Chạy `mvn validate` có tự chạy AntRun không?

**Đáp án:** Không, vì AntRun chỉ được **quản lý** và không có lifecycle default binding cho AntRun trong packaging `jar`. Muốn chạy execution này, khai plugin AntRun trong `build/plugins` của child (hoặc cấu hình usage tương đương). Đây là snippet plugin management, chưa phải POM đầy đủ.

**Bài 2:** Child `jar` không khai `maven-compiler-plugin` trong `build/plugins` nhưng parent `pluginManagement` pin Compiler `3.13.0` với release `17`. Chạy `mvn compile` có compile Java không?

**Đáp án:** Có, theo lifecycle default binding của packaging `jar`. Managed version/config được dùng cho compiler khi Maven thực thi plugin đó. Điều kiện là JDK/toolchain và plugin tương thích, source hợp lệ và các dependency resolve thành công.

**Bài 3:** Parent khai AntRun execution trong `build/plugins`, không đặt `<inherited>false</inherited>`. Child không tự khai AntRun. Có thể plugin ấy chạy trong child không?

**Đáp án:** Có. `build/plugins` của parent thường được kế thừa, gồm các executions theo quy tắc Maven model. Cần xem effective POM để chắc chắn trong tình huống cụ thể.

**Bài 4:** Một plugin có hai executions có `id` khác nhau, cả hai bind cùng goal vào `validate`. Có thể goal bị chạy hai lần không?

**Đáp án:** Có. Hai execution khác nhau có thể đều tham gia lifecycle. Nếu bạn đang muốn override execution từ parent, dùng cùng ID có chủ đích và xác minh effective POM.

**Bài 5:** Bạn muốn áp dụng JaCoCo/Checkstyle cho một số module nhưng không phải toàn bộ reactor. Nên làm gì?

**Đáp án:** Đặt version/config/executions được quản lý tại parent `pluginManagement`, cho những child được chọn khai plugin trong `build/plugins`; hoặc dùng profile/parent phù hợp nếu chính sách khác. Đừng áp đặt một execution ở `build/plugins` của parent rồi kỳ vọng tất cả child tự loại nó.

## 18. Checklist trước khi kết luận cấu hình plugin đúng

- [ ] Plugin được khai tại đúng chỗ: `build/plugins` hay `build/pluginManagement/plugins`?
- [ ] Biết plugin đó được gọi bởi **default lifecycle binding** hay bởi **custom execution**.
- [ ] Mọi plugin quan trọng có version pin, không dựa vào version tùy chọn.
- [ ] Nếu là plugin tùy chọn, module cần dùng đã khai plugin trong `build/plugins` chưa?
- [ ] Execution có `id`, `goals`, `phase` phù hợp chưa?
- [ ] Có nguy cơ goal chạy hai lần vì default binding và custom execution không?
- [ ] Plugin-level configuration và execution-level configuration đặt đúng nơi chưa?
- [ ] Parent inheritance, `<inherited>`, active profiles và merge rules đã được xét chưa?
- [ ] `dependencyManagement`/BOM không bị nhầm với `pluginManagement`.
- [ ] Các plugin dependencies không bị nhầm với classpath dependencies của ứng dụng.
- [ ] Đã so sánh `help:effective-pom` với log build ở đúng module.
- [ ] Đã kiểm tra `mvn -version` và Java release/toolchain khi gặp lỗi compiler.
- [ ] Đã chạy `mvn clean verify` và kiểm tra output/test phù hợp sau khi thay đổi policy.

**Ghi nhớ:** `build/plugins` là nơi **sử dụng build plugin** và cấu hình các executions mong muốn; `build/pluginManagement` là nơi **quản lý những thông số sẽ được áp dụng khi plugin được sử dụng**. Những plugin **đã được packaging bind mặc định** (như Compiler cho `jar`) vẫn có thể thực thi và nhận cấu hình từ management. Muốn hiểu chính xác build chạy gì, xem **effective POM + lifecycle mapping + build log**, không chỉ đếm số dòng plugin trong POM.

## Tài liệu Apache Maven chính thức

- [POM Reference — Build, Plugins, Plugin Management](https://maven.apache.org/pom.html)
- [Guide to Configuring Plug-ins — Configuration, Executions, Inheritance](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Introduction to the Build Lifecycle — Default Bindings by Packaging](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Guide to Configuring Default Mojo Executions](https://maven.apache.org/guides/mini/guide-default-execution-ids.html)
- [Maven AntRun Plugin — Configuring Ant Tasks](https://maven.apache.org/plugins/maven-antrun-plugin/usage.html)
- [Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
