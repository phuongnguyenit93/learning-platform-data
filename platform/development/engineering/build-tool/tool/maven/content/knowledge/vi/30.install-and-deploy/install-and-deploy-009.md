# Maven Reactor: trì hoãn install hoặc deploy đến cuối reactor khi phù hợp

## 1. Vì sao cần trì hoãn việc cài đặt hoặc xuất bản artifact?

Trong Maven, một dự án nhiều mô-đun (multi-module) có thể gồm các thư viện lõi, ứng dụng dùng thư viện đó, plugin nội bộ và mô-đun kiểm thử chất lượng. Nếu mỗi mô-đun được cài vào local repository hoặc đăng lên remote repository ngay khi đi qua phase tương ứng, **mô-đun đầu có thể đã được ghi đi trước khi mô-đun cuối thất bại**.

Giả sử reactor chạy nối tiếp:

~~~text
reactor-deferred-publish (parent POM)
    |
    +-- core-lib        --> SUCCESS
    |
    +-- cli-app         --> SUCCESS (phụ thuộc core-lib)
    |
    +-- quality-check   --> FAILURE (một test thất bại có chủ ý)
~~~

Nếu không trì hoãn:

~~~text
core-lib:      install hoặc deploy ngay --> đã ghi artifact
cli-app:       install hoặc deploy ngay --> đã ghi artifact
quality-check: test FAIL               --> reactor BUILD FAILURE
~~~

Kết quả là repository có thể chứa **một phần các artifact của phiên build chưa hoàn chỉnh**. Điều này đặc biệt nguy hiểm khi repository được người khác hoặc hệ thống release dùng làm nguồn dependency.

Maven cung cấp hai cơ chế cấu hình tại plugin:

- `maven-install-plugin`: tham số `installAtEnd`.
- `maven-deploy-plugin`: tham số `deployAtEnd`.

Đặt `true` khiến plugin **thu lại thao tác cài đặt/đăng tải và xử lý muộn**, thay vì mỗi module xử lý ngay tại phase của mình. Điều này giảm nguy cơ xuất bản một phần do **một module khác fail trước khi loạt thao tác được bắt đầu**. Nhưng điều cần hiểu chính xác: **không có bảo đảm transaction atomic hoặc rollback**, nhất là khi lỗi phát sinh ngay trong batch cài/đăng tải.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt phase `package`, `verify`, `install` và `deploy`.
2. Hiểu Maven local repository khác remote repository như thế nào.
3. Biết ý nghĩa, giá trị mặc định và tính chất của `installAtEnd`, `deployAtEnd`.
4. Dùng version plugin Maven Install **3.1.4** và Deploy **3.1.4** trong POM Maven 3.9.x / Java17.
5. Phân tích chính xác ảnh hưởng khi một module cuối reactor fail.
6. So sánh `true`/`false` với ví dụ reactor gồm module phụ thuộc và module kiểm thử độc lập.
7. Dùng local repository tách biệt để quan sát install mà không đụng artifact của dự án thật.
8. Thử deploy **chỉ vào file-based repository cục bộ** trong môi trường thực hành, không publish lên server tổ chức.
9. Hiểu vì sao at-end **không thay staging/promotion/rollback** của repository manager.
10. Tránh các bẫy `-pl`, `-am`, `-rf`, `-fn`, `-T`, mixed plugin configurations và những modules không được bind deploy.
11. Kiểm tra logs/artifacts/repository thực, thay vì chỉ thấy `BUILD SUCCESS` hoặc tên file trong `target`.
12. Chọn thời điểm bật deferred install/deploy theo nhu cầu phát triển, CI và release.

**Phạm vi phiên bản:** POM mẫu dùng Maven **3.9.x**, Java **17**, Install Plugin **3.1.4**, Deploy Plugin **3.1.4**, Compiler Plugin **3.14.1**, Surefire **3.5.4**, JAR Plugin **3.4.2** và JUnit Jupiter **5.11.4**. Các version được ghim để ví dụ dễ tái hiện, không khẳng định đây là những phiên bản mới nhất.

---

## 2. Maven lifecycle: install và deploy là hai việc khác nhau

Maven default lifecycle đi theo thứ tự rút gọn:

~~~text
validate
   |
   v
compile
   |
   v
test
   |
   v
package
   |
   v
verify
   |
   v
install
   |
   v
deploy
~~~

| Lệnh | Kết quả trọng tâm |
| --- | --- |
| `mvn package` | Compile/test/package theo lifecycle cho artifact chính |
| `mvn verify` | Chạy tới phase verify, gồm những checks được bind |
| `mvn install` | Chạy qua verify, rồi ghi project POM/artifacts vào **local Maven repository** |
| `mvn deploy` | Chạy qua install, rồi publish project POM/artifacts tới **remote repository** đã cấu hình |

### 2.1. Install không phải deploy

`maven-install-plugin:install` thường đưa artifact vào local repository, mặc định nằm tại:

~~~text
~/.m2/repository
~~~

Đây là đường dẫn mặc định, không phải bắt buộc: Maven settings hoặc tham số `-Dmaven.repo.local` có thể thay đổi. Một file `target/core-lib-1.0.0-SNAPSHOT.jar` chưa mặc nhiên có mặt ở local repository; `package` tạo file, `install` cài file.

`maven-deploy-plugin:deploy` đưa artifact tới **remote Maven repository**, ví dụ repository manager nội bộ. URL đích và quyền truy cập có thể đến từ `distributionManagement`, Maven settings (credentials theo `server id`) hoặc tùy chọn `altDeploymentRepository`. Nó không phải “đưa ứng dụng lên server để chạy” theo nghĩa deploy Kubernetes/container trực tiếp.

### 2.2. Gọi deploy cũng đi qua install

Vì phase `deploy` nằm sau `install` trong cùng default lifecycle:

~~~bash
mvn clean deploy
~~~

thông thường chạy cả install goals rồi mới deploy goals. Vì vậy, nếu mục tiêu là **không ghi bất kỳ artifact chưa đạt chất lượng nào ra local hoặc remote repository**, phải đánh giá **cả hai** tham số `installAtEnd` và `deployAtEnd`, không chỉ một.

### 2.3. Artifact được install/deploy gồm những gì?

Một module packaging `jar` thường có POM và main JAR. Nếu trong lifecycle các plugin như Source, Javadoc, Assembly hoặc Shade đã **attach** thêm artifacts, Install/Deploy Plugin cũng có thể xử lý chúng tùy cấu hình.

Ví dụ:

~~~text
core-lib-1.0.0-SNAPSHOT.pom
core-lib-1.0.0-SNAPSHOT.jar
core-lib-1.0.0-SNAPSHOT-sources.jar
~~~

Đây là ví dụ khi project thực sự tạo/attach sources JAR; bài thực hành phía dưới **không** cấu hình Source Plugin nên đừng mong file sources JAR tự xuất hiện.

---

## 3. Plugin Install: installAtEnd

Tham số cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-install-plugin</artifactId>
    <version>3.1.4</version>
    <configuration>
        <installAtEnd>true</installAtEnd>
    </configuration>
</plugin>
~~~

Goal `install:install` được bind mặc định vào phase `install` cho packaging thích hợp.

Theo tài liệu Install Plugin 3.1.4:

- `installAtEnd` xuất hiện từ phiên bản plugin **2.5**.
- Kiểu dữ liệu: `boolean`.
- Giá trị mặc định: **`false`**.
- User property: **`installAtEnd`**.
- Khi bật, plugin trì hoãn việc install của các projects trong multi-module build. Nếu build thất bại trước khi quá trình cài đặt deferred bắt đầu, không có loạt artifact reactor mới nào được install theo cơ chế đó.
- Tài liệu còn ghi tính năng là **experimental**; nên kiểm tra behavior thực tế theo version và build topology của project.

### 3.1. Không bật: false

~~~text
root       --> install POM ngay
core-lib   --> install POM/JAR ngay
cli-app    --> install POM/JAR ngay
quality    --> test FAILURE
~~~

Với reactor nối tiếp mẫu, artifact root/core/cli có thể đã nằm trong local repo. Những file đó là kết quả của các modules đã thành công đến phase install nhưng **toàn reactor cuối cùng không đạt**.

### 3.2. Bật: true

~~~text
root       --> queue install
core-lib   --> queue install
cli-app    --> queue install
quality    --> test FAILURE trước install
               |
               v
     deferred install không được thực hiện
~~~

Khi mô-đun cuối fail **trước khi batch bắt đầu**, Install Plugin không cài loạt artifacts reactor của invocation đó. Các JAR build đã tạo ở `target` có thể vẫn còn; chúng **không đồng nghĩa** đã được cài vào local repository.

### 3.3. InstallAtEnd không xóa artifact đã có

Nếu local repository đã có `core-lib:1.0.0-SNAPSHOT` từ một build trước, deferred install thất bại **không gỡ file cũ**. Để kiểm chứng thực nghiệm, dùng **local repository riêng, mới** cho mỗi trường hợp. Không xóa toàn bộ `~/.m2` để xem hiệu ứng.

### 3.4. Không phải transaction database

Ngay cả khi mọi module build xong và bắt đầu deferred install, lỗi filesystem, permission, full disk hoặc lỗi ghi metadata giữa batch vẫn có thể để lại một số artifacts đã được ghi. `installAtEnd=true` giảm rủi ro do module build fail **trước batch**, không có cơ chế bảo đảm tự rollback toàn bộ local repository nếu batch đang chạy gặp sự cố.

---

## 4. Plugin Deploy: deployAtEnd

Cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-deploy-plugin</artifactId>
    <version>3.1.4</version>
    <configuration>
        <deployAtEnd>true</deployAtEnd>
    </configuration>
</plugin>
~~~

Goal `deploy:deploy` được bind mặc định vào phase `deploy` trong default lifecycle thích hợp.

Theo tài liệu Deploy Plugin 3.1.4:

- `deployAtEnd` có từ plugin **2.8**.
- Kiểu dữ liệu: `boolean`.
- Giá trị mặc định: **`false`**.
- User property: **`deployAtEnd`**.
- Khi bật, plugin trì hoãn các uploads của reactor, thay vì publish từng module ngay khi nó tới phase deploy.

### 4.1. Lợi ích rõ nhất

Không deferred deploy:

~~~text
core-lib  -> uploaded
cli-app   -> uploaded
quality   -> test FAIL
reactor   -> BUILD FAILURE
remote    -> đã nhận một phần artifacts
~~~

Deferred deploy (lỗi xảy ra trước đợt upload):

~~~text
core-lib  -> queued
cli-app   -> queued
quality   -> test FAIL
reactor   -> BUILD FAILURE
remote    -> không nhận batch deferred artifacts mới
~~~

Đây là rủi ro mà `deployAtEnd=true` muốn giảm thiểu.

### 4.2. Cảnh báo quan trọng: không atomic, không rollback

**Không nói rằng deployAtEnd là “giao dịch tất cả hoặc không gì cả” trong mọi hoàn cảnh.** Khi batch upload đã bắt đầu:

- Upload một số artifacts có thể thành công trước khi mạng/repository lỗi.
- Một số repository có thể đã nhận đủ artifacts, các repository khác chưa nhận.
- Có thể có trạng thái metadata/checksum cần đối chiếu.
- Không có tự động rollback các upload đã thành công.
- Nếu một plugin/config khác được để `deployAtEnd=false`, các uploads tức thời đó không thể bị “thu hồi” bởi batch deferred của plugin khác.

Các tài liệu Deploy Plugin mới hơn còn cảnh báo rằng batch có thể được flush tại **module cuối có deploy execution**, không nhất thiết là module cuối bất kỳ trong reactor. Nếu còn những module chạy sau đó nhưng **không tham gia deploy execution** (ví dụ integration-test aggregator), chúng vẫn có thể fail sau khi artifact được publish. Vì vậy không dựa mù quáng vào chữ “end” khi thiết kế một reactor rất phức tạp.

**Kết luận kỹ thuật:** deferred deploy là **cơ chế giảm xác suất partial publication do build failure**, không phải release transaction. Với release nghiêm ngặt, dùng repository manager hỗ trợ staging, validation và **promote theo chính sách**; cần cả kiểm thử trước publish và quy trình xử lý khi batch upload lỗi.

### 4.3. Deploy không thể chạy nếu chưa có đích

Chỉ thêm `deployAtEnd=true` không cung cấp repository URL hoặc credentials. Để deploy thật, cần `distributionManagement` hoặc `altDeploymentRepository` thích hợp. Bài sẽ chỉ minh họa bằng **file-based repository cục bộ**; tuyệt đối không cần credentials server công ty.

---

## 5. So sánh tức thời và deferred

| Tình huống | installAtEnd=false | installAtEnd=true | deployAtEnd=false | deployAtEnd=true |
| --- | --- | --- | --- | --- |
| Tất cả module thành công | Install khi từng module tới phase | Install hàng loạt muộn | Upload khi từng module tới phase | Upload hàng loạt muộn |
| Module cuối fail ở test trước batch | Module trước có thể đã install | Batch deferred không install | Module trước có thể đã upload | Batch deferred không upload |
| Lỗi ghi/đẩy ngay giữa batch | Các ghi trước có thể tồn tại | Các ghi trước trong batch có thể tồn tại | Các upload trước có thể tồn tại | Các upload trước trong batch có thể tồn tại |
| Artifact có sẵn từ lần build cũ | Vẫn có thể tồn tại | Vẫn có thể tồn tại | Vẫn có thể tồn tại ở remote | Vẫn có thể tồn tại ở remote |
| Phù hợp CI/release nhiều module | Cần xem rủi ro partial | Thường hữu ích khi cần giảm partial install | Rủi ro publish một phần | Thường hữu ích nhưng chưa đủ thay staging |

Không áp dụng cột deploy cho lệnh `mvn install`: command này không tới phase deploy. Tương tự, `mvn verify` không tới install/deploy.

### 5.1. At-end không đổi dependency graph

`core-lib` phải được build trước `cli-app` vì cli-app khai Maven dependency vào core. Reactor có thể resolve dependencies giữa các modules trong cùng invocation từ workspace/reactor artifacts, nên **không phải install core vào local repo trước rồi CLI mới compile được** trong một full reactor build hợp lệ.

Nếu chạy chỉ một child module không kéo các dependencies cần thiết vào reactor, Maven có thể phải resolve core từ local/remote repository; lúc đó deferred install không tự chữa dependency thiếu. Cần hiểu `-pl`/`-am`.

---

## 6. Ví dụ runnable: ba module và test fail ở module cuối

Tạo cấu trúc sau:

~~~text
reactor-deferred-publish/
├── pom.xml
├── core-lib/
│   ├── pom.xml
│   └── src/main/java/vn/example/core/MathOps.java
├── cli-app/
│   ├── pom.xml
│   └── src/main/java/vn/example/cli/Main.java
└── quality-check/
    ├── pom.xml
    └── src/
        ├── main/java/vn/example/quality/QualityGate.java
        └── test/java/vn/example/quality/QualityGateTest.java
~~~

Tạo đúng **8 file**: 4 POM và 4 Java files.

Đồ thị:

~~~text
reactor-deferred-publish (parent + aggregator)
     |
     +-- core-lib --------------> cli-app
     |
     +-- quality-check (độc lập; khai cuối)
~~~

Root `<modules>` liệt kê `core-lib`, `cli-app`, `quality-check`. Với reactor **nối tiếp** và không có quan hệ khác, module kiểm tra được thực hiện sau core/cli. Nếu bật `-T` song song, không được dự đoán thứ tự hoàn thành giống ví dụ nối tiếp.

Mô-đun `quality-check` có 2 test JUnit 5; một test sẽ fail khi nhận Maven property:

~~~bash
-Ddemo.fail.final=true
~~~

Nhờ đó bạn có thể tạo lỗi **muộn ở phase test** mà không chỉnh Java source/POM.

### 6.1. Yêu cầu

- JDK 17+.
- Maven 3.9.x.
- Mạng/repository có thể resolve JUnit và các Maven plugins khi lần đầu build.
- Terminal đang đứng tại root `reactor-deferred-publish`.
- Không dùng remote repository thật hoặc credentials production trong bài thực hành.

---

## 7. Root POM hoàn chỉnh

File `reactor-deferred-publish/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example.reactor</groupId>
    <artifactId>reactor-deferred-publish</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core-lib</module>
        <module>cli-app</module>
        <module>quality-check</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <demo.fail.final>false</demo.fail.final>
        <installAtEnd>true</installAtEnd>
        <deployAtEnd>true</deployAtEnd>
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
                <configuration>
                    <systemPropertyVariables>
                        <demo.fail.final>${demo.fail.final}</demo.fail.final>
                    </systemPropertyVariables>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-install-plugin</artifactId>
                <version>3.1.4</version>
                <configuration>
                    <installAtEnd>${installAtEnd}</installAtEnd>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-deploy-plugin</artifactId>
                <version>3.1.4</version>
                <configuration>
                    <deployAtEnd>${deployAtEnd}</deployAtEnd>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.1. Giải thích những chi tiết quan trọng

- Root `packaging=pom` chỉ là parent/aggregator, không tạo Java JAR của root.
- Các child POM khai `<parent>` trỏ về root, nên thừa kế groupId/version/properties/plugins.
- `core-lib` chứa class Java; `cli-app` khai dependency Maven thực sự vào core-lib.
- `quality-check` là mô-đun độc lập, nằm cuối danh sách module để dễ quan sát lỗi muộn khi build nối tiếp.
- `demo.fail.final=false` là giá trị mặc định; Maven CLI `-Ddemo.fail.final=true` đổi giá trị được Surefire truyền vào JVM test.
- `installAtEnd` và `deployAtEnd` là Maven properties có mặc định `true`. Phần plugin config dùng `${installAtEnd}` và `${deployAtEnd}` để bạn có thể **đổi giá trị từ CLI trong bài thực hành** mà không sửa POM.
- Install/Deploy Plugin được đặt ở `build/plugins` (được các child kế thừa), **không chỉ** ở `pluginManagement`. Nhờ đó các plugin config được áp dụng trong default lifecycle của từng module.
- Không cần bind lại goals install/deploy thành custom executions: những goals này đã được Maven bind vào phase theo packaging/lifecycle phù hợp.

Nếu bạn thay plugin config bằng literal `<installAtEnd>true</installAtEnd>`, việc dùng `-DinstallAtEnd=false` có thể **không ghi đè literal** theo cách bạn mong muốn. POM mẫu cố ý dùng property interpolation để các thí nghiệm có thể chuyển mode bằng CLI.

---

## 8. core-lib: module thư viện

### 8.1. core-lib/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-deferred-publish</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>

    <artifactId>core-lib</artifactId>
    <packaging>jar</packaging>
</project>
~~~

### 8.2. core-lib/src/main/java/vn/example/core/MathOps.java

~~~java
package vn.example.core;

public final class MathOps {
    private MathOps() {
    }

    public static int multiply(int left, int right) {
        return Math.multiplyExact(left, right);
    }
}
~~~

Đây là class Java17 biên dịch được, không cần thư viện bên ngoài. Tên package, file, class phải khớp đường dẫn.

---

## 9. cli-app: module phụ thuộc core-lib

### 9.1. cli-app/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-deferred-publish</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>

    <artifactId>cli-app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example.reactor</groupId>
            <artifactId>core-lib</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>
    </dependencies>
</project>
~~~

### 9.2. cli-app/src/main/java/vn/example/cli/Main.java

~~~java
package vn.example.cli;

import vn.example.core.MathOps;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("answer=" + MathOps.multiply(6, 7));
    }
}
~~~

Main class in chính xác:

~~~text
answer=42
~~~

Dự án không cấu hình executable manifest cho cli-app JAR; vì thế **đừng dùng `java -jar cli-app.jar` và mong ứng dụng tự tìm core-lib**. Bài sẽ chạy bằng explicit classpath ở mục 12.

### 9.3. Tại sao CLI vẫn build khi installAtEnd=true?

Trong một full reactor invocation, Maven biết core-lib và cli-app cùng thuộc reactor. Khi core-lib đã compile/package thành công, Maven có thể lấy artifact/classes từ reactor để phục vụ cli-app, thay vì yêu cầu core-lib phải được install vào local Maven repository trước.

**Không nhầm install với dependency resolution trong reactor.** Deferred install không có nghĩa cli-app bị mất dependency nếu reactor selection đúng. Tuy nhiên nếu bạn chỉ chọn cli-app mà không build core-lib hoặc chưa có core artifact ở repository, build có thể fail unresolved dependency; khi đó dùng `-pl :cli-app -am`.

---

## 10. quality-check: module độc lập và test có thể fail ở cuối

### 10.1. quality-check/pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example.reactor</groupId>
        <artifactId>reactor-deferred-publish</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </parent>

    <artifactId>quality-check</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 10.2. quality-check/src/main/java/vn/example/quality/QualityGate.java

~~~java
package vn.example.quality;

public final class QualityGate {
    private QualityGate() {
    }

    public static String status() {
        return "READY";
    }
}
~~~

### 10.3. quality-check/src/test/java/vn/example/quality/QualityGateTest.java

~~~java
package vn.example.quality;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

import org.junit.jupiter.api.Test;

class QualityGateTest {
    @Test
    void statusIsStable() {
        assertEquals("READY", QualityGate.status());
    }

    @Test
    void failOnlyWhenRequested() {
        assertFalse(
                Boolean.getBoolean("demo.fail.final"),
                "Intentional late failure to demonstrate install/deploy deferral"
        );
    }
}
~~~

Hai tests:

- `statusIsStable`: luôn PASS nếu class giữ nguyên.
- `failOnlyWhenRequested`: PASS với default `demo.fail.final=false`; FAIL khi CLI truyền `-Ddemo.fail.final=true`.

Root Surefire configuration truyền Maven property vào test JVM qua `systemPropertyVariables`. Mô-đun quality-check nằm cuối reactor ở build nối tiếp, nên khi test này fail, **những mô-đun trước đã tới phase install/deploy nếu không deferred**.

Bài dùng **2 JUnit tests tổng cộng**, không phải 2 tests ở mỗi module. Core và CLI không có unit tests riêng; chúng vẫn phải compile/package thành công.

---

## 11. Baseline: chỉ verify, chưa install/deploy

Tại root project:

~~~bash
java -version
mvn -version
mvn clean verify
~~~

Với Maven/JDK, nguồn và dependencies phù hợp, dự kiến:

~~~text
reactor-deferred-publish ... SUCCESS
core-lib .................. SUCCESS
cli-app ................... SUCCESS
quality-check ............. SUCCESS

BUILD SUCCESS
~~~

Trong Surefire report của quality-check, dự kiến:

~~~text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
~~~

Maven có thể sinh thêm các file trong `target`. Các files chính:

~~~text
core-lib/target/core-lib-1.0.0-SNAPSHOT.jar
cli-app/target/cli-app-1.0.0-SNAPSHOT.jar
quality-check/target/quality-check-1.0.0-SNAPSHOT.jar
quality-check/target/surefire-reports/TEST-vn.example.quality.QualityGateTest.xml
~~~

**Chú ý:** `mvn verify` dừng trước install/deploy, vì thế chưa thể dùng riêng output của nó để chứng minh deferred install/deploy đã hoạt động.

### 11.1. Java stdout chính xác

Linux/macOS dùng `:` trong Java classpath:

~~~bash
java -cp "cli-app/target/classes:core-lib/target/classes" vn.example.cli.Main
~~~

Windows CMD hoặc PowerShell dùng `;`:

~~~bat
java -cp "cli-app\target\classes;core-lib\target\classes" vn.example.cli.Main
~~~

Stdout:

~~~text
answer=42
~~~

Đây là lệnh chạy chương trình **sau khi source đã được compile thành công**, không phải stdout tự sinh bởi `mvn verify`.

---

## 12. Thí nghiệm install tức thời: installAtEnd=false

Để không làm nhiễm `~/.m2/repository` của bạn, bài dùng một **Maven local repository riêng** chưa được sử dụng trước đó. Tại root dự án, chạy:

~~~bash
mvn -Dmaven.repo.local=.m2-immediate "-DinstallAtEnd=false" "-Ddemo.fail.final=true" clean install
~~~

Lưu ý: vì POM đã đặt `<installAtEnd>${installAtEnd}</installAtEnd>`, CLI property `installAtEnd=false` thay được giá trị của plugin config cho invocation này.

Với reactor nối tiếp, dự kiến:

~~~text
reactor-deferred-publish ... SUCCESS
core-lib .................. SUCCESS
cli-app ................... SUCCESS
quality-check ............. FAILURE

BUILD FAILURE
~~~

Điểm quan trọng: mặc dù toàn reactor FAIL khi quality-check test fail, các modules root/core-lib/cli-app **đã có thể được install** tại thời điểm từng module qua phase install. Điều này cho thấy rủi ro cài đặt artifact của một phiên build chưa đạt chất lượng toàn reactor.

### 12.1. Kiểm tra local repo đúng chỗ

Các đường dẫn mang tính logic, với `-Dmaven.repo.local=.m2-immediate`:

~~~text
.m2-immediate/vn/example/reactor/
  reactor-deferred-publish/1.0.0-SNAPSHOT/
  core-lib/1.0.0-SNAPSHOT/
  cli-app/1.0.0-SNAPSHOT/
~~~

Maven thường tạo metadata và artifact files trong các thư mục này. Không hardcode rằng mọi metadata/file checksum sẽ có một danh sách tuyệt đối giống nhau trên mọi hệ điều hành/plugin version.

Bạn có thể kiểm tra bằng công cụ duyệt file hoặc các lệnh read-only phù hợp, ví dụ trên Bash:

~~~bash
find .m2-immediate/vn/example/reactor -type f
~~~

**Không xóa hàng loạt** `~/.m2` để thử. Thư mục `.m2-immediate` này dành riêng cho demo; nếu trước đó bạn đã chạy lại cùng command, nó có thể chứa artifact từ lượt cũ. Chỉ so sánh trạng thái khi dùng repository mới hoặc kiểm tra timestamps/logs gắn với invocation.

### 12.2. Lỗi nằm ở test cuối

Báo cáo:

~~~text
quality-check/target/surefire-reports/
  TEST-vn.example.quality.QualityGateTest.xml
~~~

Dự kiến chứa 2 tests, 1 failure, 0 errors. Lỗi là có chủ đích, không phải lỗi source Java hoặc plugin. Vì quality-check FAIL trước phase package/install, module này không hoàn tất install.

---

## 13. Thí nghiệm deferred install: installAtEnd=true

Dùng repository khác, chưa có artifacts của demo:

~~~bash
mvn -Dmaven.repo.local=.m2-deferred "-DinstallAtEnd=true" "-Ddemo.fail.final=true" clean install
~~~

Root POM cũng đã mặc định `installAtEnd=true`, nhưng khai tường minh trên CLI để dễ so sánh.

Kỳ vọng reactor:

~~~text
reactor-deferred-publish ... SUCCESS
core-lib .................. SUCCESS
cli-app ................... SUCCESS
quality-check ............. FAILURE

BUILD FAILURE
~~~

**Điểm khác:** root/core/cli chưa được flush vào local repo vì module cuối fail **trước khi deferred install bắt đầu**. Nếu repository `.m2-deferred` thật sự mới, không có artifacts demo dưới nhóm:

~~~text
.m2-deferred/vn/example/reactor/
~~~

Plugin và dependency artifacts từ Maven Central vẫn có thể đã được tải/cached trong `.m2-deferred`; chỉ phần **GAV của chính demo** được kỳ vọng chưa xuất hiện.

### 13.1. Đừng nhầm target với installed artifacts

Lệnh `clean install` có thể đã tạo:

~~~text
core-lib/target/core-lib-1.0.0-SNAPSHOT.jar
cli-app/target/cli-app-1.0.0-SNAPSHOT.jar
~~~

trước khi quality-check thất bại. File còn ở `target` là **build output**, không chứng minh Install Plugin đã ghi thành công vào local repository.

### 13.2. Kiểm chứng qua logs

Khi bật deferred install, các logs có thể cho biết hoạt động install được deferred/queued. Thứ tự và câu chữ log thay đổi theo plugin version. Đọc Maven command, plugin config và đường dẫn repository thật; không dựa duy nhất vào một chuỗi log cứng.

---

## 14. Thí nghiệm deferred install thành công

Sử dụng local repository riêng thứ ba:

~~~bash
mvn -Dmaven.repo.local=.m2-success "-DinstallAtEnd=true" "-Ddemo.fail.final=false" clean install
~~~

Khi test ở quality-check PASS và mọi plugin/IO hoạt động bình thường:

~~~text
reactor-deferred-publish ... SUCCESS
core-lib .................. SUCCESS
cli-app ................... SUCCESS
quality-check ............. SUCCESS

BUILD SUCCESS
~~~

Deferred install có thể ghi artifacts của root, core-lib, cli-app và quality-check vào local repository:

~~~text
.m2-success/vn/example/reactor/
  reactor-deferred-publish/1.0.0-SNAPSHOT/
  core-lib/1.0.0-SNAPSHOT/
  cli-app/1.0.0-SNAPSHOT/
  quality-check/1.0.0-SNAPSHOT/
~~~

Lưu ý root packaging `pom`: artifact chính của root là POM, không phải JAR. Ba child packaging `jar`: artifact chính là JAR cùng POM. InstallAtEnd không tự gộp chúng thành một JAR lớn.

### 14.1. Vì sao dùng ba local repositories?

Nếu thí nghiệm `false` đã cài artifact thành công, rồi bạn bật `true` nhưng dùng **cùng repository**, các artifacts cũ vẫn có thể tồn tại. Bạn dễ kết luận sai “installAtEnd không hoạt động”. Tách `.m2-immediate`, `.m2-deferred` và `.m2-success` giúp so sánh cơ chế mà không phải xóa caches chung.

Đánh đổi là lần đầu mỗi repository riêng có thể phải tải lại plugin/dependencies, mất thời gian và cần mạng. Với pipeline thật, có thể dùng cache nhưng phải so khớp artifact version, checksum và build provenance.

---

## 15. Thực hành deploy an toàn: chỉ dùng file repository cục bộ

**Không chạy `mvn deploy` tới repository tổ chức hay Maven Central chỉ để thử.** Bài này không cấu hình `distributionManagement` và không có credentials. Nếu muốn quan sát deploy, có thể dùng một repository file **cục bộ chỉ dành cho thử nghiệm** thông qua user property `altDeploymentRepository`.

### 15.1. Tạo destination riêng trên Linux/macOS Bash

~~~bash
STAGING_DIR="$(mktemp -d)"
printf 'Staging directory: %s\n' "$STAGING_DIR"
~~~

`mktemp -d` tạo thư mục tạm mới; kiểm tra output để biết destination thực. Không dùng một đường dẫn đang có dữ liệu quan trọng. Lệnh sau gửi artifact vào filesystem local qua `file://`, **không đăng lên remote HTTP**:

~~~bash
mvn "-DinstallAtEnd=true" "-DdeployAtEnd=true" \
  "-DaltDeploymentRepository=demo-file::file://$STAGING_DIR" \
  "-Ddemo.fail.final=false" clean deploy
~~~

Với Bash, khi `STAGING_DIR` là path tuyệt đối bắt đầu bằng `/`, chuỗi `file://$STAGING_DIR` trở thành file URI dạng `file:///...`. Phần `demo-file` là repository ID tùy chọn cho demo, không chứa credentials. Maven Deploy Plugin 3.x sử dụng cú pháp `id::url` cho `altDeploymentRepository`.

Khi mọi modules PASS và file repository cho phép ghi, deploy artifacts của root/core/cli/quality có thể được xuất bản vào `STAGING_DIR`. Đây là một thử nghiệm **local file repository**, không phải phát hành production.

### 15.2. Gây lỗi trước khi deferred deploy bắt đầu

Dùng destination mới riêng:

~~~bash
FAILED_DIR="$(mktemp -d)"

mvn "-DinstallAtEnd=true" "-DdeployAtEnd=true" \
  "-DaltDeploymentRepository=demo-file::file://$FAILED_DIR" \
  "-Ddemo.fail.final=true" clean deploy
~~~

Nếu quality-check JUnit test FAIL trước khi tới deploy, kỳ vọng **không có artifacts demo mới** được upload bởi deferred deploy trong `FAILED_DIR`. Đọc Reactor Summary, exit status và nội dung directory để kiểm tra.

**Điều kiện:** không có plugin khác deploy sớm với `deployAtEnd=false`, không có event ngoài reactor sửa cùng repository và đường dẫn thực sự mới. Không khẳng định “mọi file trong toàn thư mục bằng 0” nếu repository manager/công cụ khác cũng dùng destination ấy.

### 15.3. Nếu muốn quan sát chế độ tức thời

Trong một destination **mới khác**:

~~~bash
IMMEDIATE_DIR="$(mktemp -d)"

mvn "-DinstallAtEnd=false" "-DdeployAtEnd=false" \
  "-DaltDeploymentRepository=demo-file::file://$IMMEDIATE_DIR" \
  "-Ddemo.fail.final=true" clean deploy
~~~

Lúc này root/core/cli có thể đã được upload khi chúng tới phase deploy, trước khi quality-check fail ở test. Đây là một minh họa của **partial publication**. Chỉ chạy trong sandbox file repository tạm, không dùng server release thật.

### 15.4. Trên Windows thì sao?

Các lệnh `mktemp` và `file://$STAGING_DIR` ở trên là **Bash/Linux/macOS**, không phải PowerShell/CMD. Trên Windows, bạn có thể:

- Chỉ thực hành deferred **install**, không cần deploy.
- Dùng một sandbox file URI tuyệt đối hợp lệ theo OS và repository manager, sau khi kiểm tra `altDeploymentRepository` đã được Maven/Wagon hiểu đúng.
- Tránh đổi một lệnh Bash thành CMD bằng cách chỉ thay dấu gạch chéo; URL và biến môi trường phải đúng cú pháp.

Bài không yêu cầu chạy deploy thật để hiểu semantics `deployAtEnd`.

---

## 16. Deploy thật cần distributionManagement và credentials phù hợp

Một POM của tổ chức thường khai repository đích, ví dụ **trích đoạn minh họa, không đưa vào demo**:

~~~xml
<distributionManagement>
    <repository>
        <id>releases-repo</id>
        <url>https://repo.example.invalid/releases</url>
    </repository>
    <snapshotRepository>
        <id>snapshots-repo</id>
        <url>https://repo.example.invalid/snapshots</url>
    </snapshotRepository>
</distributionManagement>
~~~

Domain `example.invalid` là địa chỉ minh họa không hoạt động; không dán nguyên vào project và kỳ vọng publish thành công.

Maven đọc credentials bằng `server id` tương ứng từ settings/CI secret injection. Không commit username/password/token vào POM. Trong release thật, repository manager có thể cấm overwrite cùng version release và có staging/promotion workflow riêng.

### 16.1. SNAPSHOT và release

Project mẫu dùng `1.0.0-SNAPSHOT` để thực hành, tránh mô phỏng publish immutable releases. Khi phát hành phiên bản release như `1.0.0`:

- Bản release có thể bị repository policy chặn overwrite.
- Nếu đã upload một phần trước khi lỗi, rerun cùng version có thể không sửa được phần cũ.
- Cần kiểm tra repo, metadata và áp dụng quy trình staging/drop/promote hoặc tăng version đúng chính sách.
- `deployAtEnd` không cung cấp rollback hay promotion tự động.

### 16.2. installAtEnd và deployAtEnd độc lập

Có thể cấu hình:

~~~xml
<installAtEnd>true</installAtEnd>
~~~

mà `deployAtEnd` vẫn false trong một plugin config khác. Khi chạy `mvn deploy`, local install được deferred nhưng remote deploy có thể diễn ra tức thời ở từng module. Ngược lại, deploy deferred mà install immediate có thể để local repo chứa một phần artifact nếu module cuối fail.

Nếu yêu cầu của bạn bao gồm **giảm ghi một phần ở cả local và remote**, hãy bật/cấu hình cả hai và kiểm tra toàn bộ effective POM.

---

## 17. Các điều kiện cần hiểu trước khi bật at-end

### 17.1. Cùng một reactor invocation

Defer at-end mang ý nghĩa rõ nhất khi **nhiều modules được build trong cùng Maven session/reactor**. Nếu chạy từng child module thành các Jenkins jobs độc lập hoặc gọi Maven nhiều lần, plugin không có một “reactor toàn hệ thống” xuyên các process để trì hoãn đồng bộ.

Ví dụ:

~~~bash
mvn -pl :core-lib install
mvn -pl :cli-app install
~~~

là hai invocations tách biệt, không tạo transaction trên toàn bộ hệ thống. Bật `installAtEnd=true` trong mỗi invocation **không thể ngăn artifacts của invocation đầu đã install trước khi invocation thứ hai fail**.

### 17.2. Phải bind plugin đúng nơi

Trong multi-module project, khai cấu hình ở parent `build/plugins` rồi để children kế thừa nếu muốn áp dụng cùng policy. Nếu chỉ khai trong `pluginManagement` mà plugin không được áp dụng vào module/goal, có thể không nhận behavior mong muốn.

Không đoán: dùng `mvn help:effective-pom` ở đúng module để xem plugin version và cấu hình `installAtEnd`/`deployAtEnd`.

### 17.3. Không bật nhầm ở một vài modules

Nếu một module dùng `installAtEnd=true` còn module khác dùng `false`, module thứ hai vẫn có thể cài ngay. Tương tự, `deployAtEnd=false` ở một plugin execution có thể publish trước batch deferred. “At end” chỉ tác động lên những executions được cấu hình/áp dụng đúng.

### 17.4. Thứ tự modules và các goal khác

Một số reactor có modules riêng cho integration tests, docs, signing, distribution hoặc aggregate reports. Nếu chúng không tham gia deploy execution nhưng vẫn còn chạy sau những module deploy-eligible, một số phiên bản/cấu trúc plugin có thể flush uploads trước khi tất cả kiểm tra cuối hoàn tất.

Bởi vậy **kiểm thử thực tế đúng graph, plugin version, lifecycle bindings và CI command** quan trọng hơn một lời khẳng định chung “at end = tất cả module đã pass”.

### 17.5. Install/deploy performance

Trì hoãn I/O có thể thay thời điểm ghi repository, mức độ tiêu thụ memory/disk và thông tin lỗi xuất hiện trên console. Trong reactor lớn, cần cân bằng số modules, timeout mạng, retries và khả năng chẩn đoán batch failure. Deferred upload không làm I/O miễn phí; nó chỉ đổi **thời điểm**.

---

## 18. Các cờ reactor liên quan

| Flag | Vai trò | Tác động cần chú ý |
| --- | --- | --- |
| `-ff` / `--fail-fast` | Dừng sớm khi project fail; mặc định | Deferred batch có thể chưa chạy |
| `-fae` / `--fail-at-end` | Tiếp tục modules không bị ảnh hưởng rồi vẫn báo failure | Có thể thu nhiều diagnostics; không phải cơ chế atomic deploy |
| `-fn` / `--fail-never` | Có thể trả exit 0 dù project failures | **Không dùng làm cổng phát hành** |
| `-pl` | Chọn một phần reactor | At-end chỉ có ý nghĩa trên phạm vi selected projects |
| `-am` | Kéo thêm reactor dependencies | Hữu ích để build child cùng các upstream cần thiết |
| `-amd` | Kéo thêm dependents | Có thể tăng phạm vi kiểm thử downstream |
| `-rf` | Resume từ một module | Không tự khôi phục rollback hay revalidate modules trước đó |
| `-T` | Parallel reactor build | Log/finish order khác, phải xét concurrency |

### 18.1. Lưu ý với -fn

Nếu command dùng `-fn`, Maven có thể bỏ qua project failure ở process exit và vẫn cố build những modules khác. Điều này rất nguy hiểm cho release flow. **Đừng dùng `-fn clean deploy` với repository production**, kể cả khi `deployAtEnd=true`. Cơ chế hoãn không thay thế việc build/test phải thực sự pass.

### 18.2. -fae phù hợp khi cần nhiều logs

~~~bash
mvn -fae clean verify
~~~

có thể thu kết quả của các nhánh độc lập và giữ exit code nonzero nếu có failure. Nếu cần publish, vẫn nên dùng CI gate rõ và quyết định publish chỉ sau khi quality checks đã hoàn tất. Đừng mặc định `-fae` làm mọi downstream được build nếu upstream module đã fail.

### 18.3. -pl/-am với ví dụ

~~~bash
mvn -pl :cli-app -am clean verify
~~~

mang core-lib vào reactor vì cli-app phụ thuộc core. Nhưng quality-check độc lập thường không thuộc phạm vi đã chọn, nên một success ở đây **không chứng minh quality-check đã pass**.

Nếu muốn demo lỗi muộn và deferred install, hãy chạy **full reactor** tại root, không chọn riêng CLI.

### 18.4. -rf không phải resume transaction

Sau khi reactor fail ở quality-check, `-rf :quality-check` có thể chỉ chạy từ module đó; các modules trước không được build lại và artifacts cần thiết có thể không nằm trong local repo nếu installAtEnd đã hoãn. Khi cần đảm bảo đồng bộ một version release, ưu tiên **rebuild toàn bộ phạm vi bắt buộc trong một invocation sạch** rồi mới install/deploy theo release policy.

---

## 19. Tại sao at-end không tương đương atomic publish?

Có ba ranh giới khác nhau:

1. **Build readiness:** các module có qua compile/test/package/verify không?
2. **Deferred operation:** bắt đầu install/deploy sau các hoạt động liên quan trong reactor, giảm rủi ro module fail muộn trước batch.
3. **Repository consistency:** nhiều files, checksums, metadata và nhiều repositories được ghi như một transaction hay không?

`installAtEnd`/`deployAtEnd` tập trung ở ranh giới số 2. Chúng **không tự cung cấp** ranh giới số 3.

Ví dụ batch deploy gồm:

~~~text
1. root POM           --> uploaded
2. core-lib POM/JAR   --> uploaded
3. cli-app POM/JAR    --> network timeout
4. quality-check      --> chưa upload
~~~

Dù batch bắt đầu ở cuối, vẫn có artifact đã được publish trước timeout. Không có rollback mặc định.

### 19.1. Cách làm release chặt chẽ hơn

- Build và unit/integration tests đầy đủ trước publish.
- Sinh artifact version nhất quán và hash/checksum.
- Publish vào **staging repository** nếu repository manager hỗ trợ.
- Xác minh số artifact, metadata, signature/SBOM/license theo policy.
- Promote staging repository chỉ sau khi kiểm tra thành công.
- Nếu lỗi, drop staging theo công cụ repository manager thay vì tự xóa một vài files từ remote release repo.
- Với immutable release, không tự retry overwrite cùng version khi có partial publication.

Deferred deploy có thể là một lớp bảo vệ **bên trong** workflow này, nhưng không thay workflow.

### 19.2. Đừng hiểu sai chữ “end”

“At end” không phải một hook tùy ý do Maven chạy sau tất cả các command của CI job. Nó áp dụng trong **Maven session/lifecycle/plugin behavior** đang chạy. Các CI steps sau `mvn deploy` (ví dụ security scan, end-to-end deployment test) vẫn có thể fail sau khi artifact đã publish. Nếu những checks ấy là điều kiện release bắt buộc, phải đưa chúng **trước** bước publish hoặc dùng staging + promotion.

---

## 20. Đọc exit code, logs và repository

### 20.1. Bash

~~~bash
mvn "-DinstallAtEnd=true" "-Ddemo.fail.final=true" clean install
status=$?
printf 'maven_exit=%s\n' "$status"
~~~

Với JUnit failure cố ý, mã thoát phải nonzero khi không dùng `-fn`/test-ignore. Nếu Bash có `set -e`, dùng `if` để bắt status và xử lý reports.

### 20.2. Bash với tee

~~~bash
set -o pipefail
mvn clean install | tee build.log
status=$?
exit "$status"
~~~

Không có `pipefail`, Bash pipeline thường trả status của `tee`, có thể che failure của Maven. Bản thân `-fn` cũng có thể khiến Maven trả `0` dù module failed; pipefail không sửa điều đó.

### 20.3. PowerShell

~~~powershell
mvn "-DinstallAtEnd=true" "-Ddemo.fail.final=true" clean install
$code = $LASTEXITCODE
Write-Output "exit_code=$code"
~~~

### 20.4. Windows CMD

~~~bat
mvn "-DinstallAtEnd=true" "-Ddemo.fail.final=true" clean install
echo exit_code=%ERRORLEVEL%
~~~

Phân biệt build process exit code và trạng thái repository. **Exit nonzero** cho biết có lỗi, nhưng không trả lời artifact nào đã kịp được install/deploy; cần kiểm tra thực tế nếu batch đã bắt đầu.

---

## 21. Troubleshooting thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `mvn verify` không tạo artifacts trong ~/.m2 | Chưa chạy phase install | Dùng `mvn install` khi thực sự cần |
| `mvn deploy` báo thiếu repository | Chưa có distributionManagement/altDeploymentRepository | Cấu hình đúng đích và credentials |
| Bật installAtEnd nhưng artifact cũ vẫn còn | Local repo có dữ liệu từ lần trước | Dùng repo tách biệt; so timestamps/provenance |
| installAtEnd=true, module cuối fail, không thấy artifacts | Deferred install chưa flush | Đúng trong thí nghiệm này |
| installAtEnd=false, module cuối fail, vẫn thấy core JAR | Core đã được install sớm | Đây là partial install |
| deployAtEnd=true nhưng remote có vài files | Lỗi giữa batch hoặc mixed configs/repo cũ | Kiểm tra logs/uploads/repo metadata |
| Project khác resolve dependency fail | Không nằm cùng reactor hoặc thiếu -am | Build đúng selection và dependencies |
| `-pl :cli-app` pass dù quality test lỗi | quality-check không được chọn | Full reactor verify trước release |
| `-rf` fail resolution | Upstream chưa được install/đã bị hoãn | Build full reactor hoặc kéo dependencies vào scope |
| Plugin config không tác dụng | Chỉ khai pluginManagement hoặc bị override/inheritance khác | Xem effective POM |
| CLI -DinstallAtEnd=false không đổi config | POM hardcode true thay vì property interpolation | Xem giá trị effective config |
| Build xanh khi có tests fail | -fn, skipTests hoặc test-failure-ignore | Loại bypass; xem Surefire reports |
| Root POM cũng được install | Packaging pom vẫn có POM artifact | Đây là hành vi bình thường |
| Các JAR được tạo nhưng chưa install | Chỉ package/verify hoặc deferred chưa flush | Phân biệt target với local repo |
| Maven dùng repo local khác dự kiến | settings.xml / -Dmaven.repo.local | Xác minh đường dẫn thực |
| Deploy fail vì 401/403 | Credentials hoặc quyền repository sai | Kiểm tra server id, CI secret injection |
| Deploy fail vì release version tồn tại | Remote repository immutable | Dùng staging/version mới theo policy |
| Parallel -T cho log thứ tự khác | Scheduler chạy modules độc lập cùng lúc | Đọc graph/summary, không đoán từ log |
| Source có 2 test nhưng báo 0 | Surefire tests bị skip hoặc discovery sai | Đọc XML reports, kiểm tra JUnit version |
| Deploy không hoàn tất hết modules | Có module không bind deploy, plugin behavior/version khác | Kiểm tra reactor graph/executions và thời điểm flush |

### 21.1. Quy trình điều tra sáu bước

1. Ghi nguyên Maven command, phase, selected modules, Maven/JDK/plugin versions.
2. Xem `mvn help:effective-pom` ở parent và child để kiểm tra plugin configurations/inheritance.
3. Đọc Reactor Summary và Surefire reports: module nào SUCCESS/FAILURE/SKIPPED?
4. Tìm thời điểm install/deploy goals thực sự chạy hoặc bị deferred trong log.
5. Kiểm tra **đúng local/remote repo**, GAV/version/classifier của artifacts mới.
6. Nếu có partial publication, **không blind retry vào release repo**; xác minh repo state, dùng staging/rollback/promotion hoặc version mới theo policy.

---

## 22. Khi nào nên bật, khi nào nên giữ mặc định?

### Nên cân nhắc installAtEnd=true khi

- Reactor có nhiều modules và một module cuối có thể fail.
- Muốn tránh cài vào local repo artifacts từ một build tổng thể chưa đạt.
- CI cần kiểm tra consistency của một tập GAV cùng revision.
- Parent POM + modules đều chia sẻ policy install rõ ràng.
- Không muốn lẫn artifacts cùng SNAPSHOT version trong local repo từ một build thất bại.

### Nên cân nhắc deployAtEnd=true khi

- Build nhiều module cần được publish cùng một đợt nếu các checks trước batch pass.
- Muốn giảm nguy cơ consumer thấy artifact một phần khi module cuối fail.
- Repository manager/pipeline đã có thêm staging/promotion/verification.
- Team kiểm chứng behavior trên đúng Maven Deploy Plugin version và reactor topology.

### Có thể giữ false khi

- Build chỉ một module, không có lợi ích đáng kể từ gom thao tác.
- Các artifacts độc lập được publish riêng có chủ đích.
- Workflow đã quản lý publish transaction ở tầng khác và cần upload theo module vì lý do riêng.
- Project/plugin có compatibility constraint hoặc pipeline muốn tiếp tục dùng semantics mặc định đã được kiểm thử.

**Không bật `true` chỉ vì có thể bật**: phải hiểu lifecycle, module graph, failure handling, repository và release policy. Với một reactor đơn giản không có remote deploy, `mvn verify` có thể là lệnh phù hợp nhất để kiểm thử, không cần phase install/deploy ở mỗi PR.

---

## 23. Bài tập thực hành

**Bài A — Đọc lifecycle.** Phân biệt `mvn verify`, `mvn install`, `mvn deploy`. Nếu chạy deploy, install có được thực thi trước không?

**Bài B — Build baseline.** Tạo 8 file của mục 6–10, chạy `mvn clean verify`. Xác nhận 4 projects SUCCESS, 2 JUnit tests PASS. Chạy CLI và kiểm tra stdout `answer=42`.

**Bài C — Kiểm tra POM.** Chỉ ra root plugin config nào điều khiển `installAtEnd` và `deployAtEnd`. Vì sao dùng expression từ properties thay vì hardcode literal?

**Bài D — Immediate install failure.** Chạy `mvn -Dmaven.repo.local=.m2-immediate -DinstallAtEnd=false -Ddemo.fail.final=true clean install`. Chỉ ra artifacts root/core/cli đã xuất hiện ở local repo dù reactor FAILURE.

**Bài E — Deferred install failure.** Lặp lại với repository mới và `-DinstallAtEnd=true`. Tại sao có JAR trong `target` nhưng không có chúng trong local repo?

**Bài F — Deferred install success.** Với repo mới thứ ba và `-Ddemo.fail.final=false`, chạy `clean install`. Có mấy Maven projects được cài thành công? Root packaging pom tạo main artifact loại nào?

**Bài G — Không atomic.** Giả sử deferred install batch đã ghi root/core rồi disk đầy ở CLI. `installAtEnd=true` có rollback root/core tự động không? Cần bước kiểm tra/phục hồi nào?

**Bài H — File-based deploy.** Chỉ trên sandbox Bash, dùng `mktemp -d` và `-DaltDeploymentRepository=demo-file::file://...` để publish một lần build PASS. Không dùng repository tổ chức.

**Bài I — Deferred deploy failure.** Trên destination sandbox khác, bật `-DdeployAtEnd=true` và `-Ddemo.fail.final=true`. Đọc logs và kiểm tra thư mục. Vì sao không có uploads mới khi test fail trước batch?

**Bài J — Immediate deploy failure.** Trên destination sandbox thứ ba, bật `-DdeployAtEnd=false` và lỗi test cuối. So sánh repository contents với Bài I.

**Bài K — Two flags.** Nếu `installAtEnd=false` nhưng `deployAtEnd=true` và module cuối fail, local repo và remote repo có thể có trạng thái khác nhau thế nào?

**Bài L — Partial repository failure.** Nếu deploy batch đã upload core nhưng mạng lỗi ở CLI, có được nói transaction atomic không? Khi dùng immutable release repository thì nên xử lý thế nào?

**Bài M — Module selection.** Chạy `mvn -pl :cli-app -am verify`. Có phải quality-check đã được test chưa? Vì sao không thể coi success của subset là success toàn hệ thống?

**Bài N — -fn và CI.** Vì sao không chạy `mvn -fn clean deploy` chỉ để “không dừng vì test fail”? Nó ảnh hưởng ra sao tới exit code và quyết định publish?

**Bài O — Effective configuration.** Dùng `mvn help:effective-pom` và kiểm tra Install/Deploy Plugin versions cùng values của `installAtEnd`/`deployAtEnd`. Khi child kế thừa plugin config, làm sao phát hiện một child override thành false?

**Bài P — Release gate.** Thiết kế pipeline có build/test, deferred deploy, staging, xác minh GAV/classifier/checksum, promote và xử lý partial failure. Chỉ rõ phần nào Maven đảm trách và phần nào cần repository manager.

---

## 24. Checklist trước khi áp dụng vào CI/release

- [ ] Phân biệt chính xác local `install` và remote `deploy`.
- [ ] Xác định reactor modules và dependency graph.
- [ ] Ghim Maven Install/Deploy Plugin versions có behavior đã thử.
- [ ] Biết hai tham số mặc định `false` ở phiên bản plugin được chọn.
- [ ] Cấu hình `installAtEnd`/`deployAtEnd` ở đúng plugin và modules.
- [ ] Kiểm tra config inheritance, overrides và effective POM.
- [ ] Nếu dùng CLI properties để đổi mode, plugin config phải tham chiếu properties.
- [ ] Không nhầm thư mục `target` với local Maven repository.
- [ ] Không nhầm `mvn verify` với `mvn install` hoặc `mvn deploy`.
- [ ] Khi so sánh, dùng local repo hoặc file repo sạch/tách biệt.
- [ ] Không để artifact cũ cùng version đánh lừa phép kiểm tra.
- [ ] Chạy đủ modules cần thiết, không chỉ một subset thiếu quality-check.
- [ ] Đọc Surefire reports, xác nhận tests đã thực thi.
- [ ] Không dùng `-fn`, `-DskipTests` hoặc ignore flags để vượt cổng chất lượng.
- [ ] Hiểu at-end không có transaction/rollback khi batch ghi/đẩy bị lỗi.
- [ ] Không coi deferred publish đã bao phủ các CI steps chạy **sau** Maven deploy.
- [ ] Dùng staging/promotion khi repository manager và policy yêu cầu.
- [ ] Không đăng release version lên remote repo thật trong bài thực hành.
- [ ] Không log hoặc commit credentials; kiểm tra đúng repository ID.
- [ ] Nếu partial publish xảy ra, kiểm kê thực trạng trước retry.
- [ ] Đảm bảo exit code của Maven được script trả lại đúng cho CI.

**Kết luận:** `installAtEnd=true` giúp trì hoãn ghi vào local Maven repository; `deployAtEnd=true` giúp trì hoãn upload lên remote Maven repository trong reactor nhiều module. Hai lựa chọn hữu ích để tránh những artifacts của module đầu bị ghi đi **trước khi lỗi ở module sau được phát hiện**, nhưng **không biến repository thành một transaction atomic**, không rollback upload/ghi thất bại giữa batch và không thay thế quality gate, staging hoặc promotion. Hãy bật khi phù hợp với toàn bộ reactor và kiểm chứng bằng artifacts, repository contents, logs và test reports của đúng invocation.

## 25. Tài liệu tham khảo chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phân biệt verify/install/deploy.
- [Apache Maven — Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): Reactor sorting, `-pl`, `-am`, `-rf` và xử lý failures.
- [Maven Install Plugin 3.1.4 — install:install](https://maven.apache.org/plugins/maven-install-plugin/install-mojo.html): `installAtEnd`, default false, scope và tính chất.
- [Maven Install Plugin — Introduction](https://maven.apache.org/plugins/maven-install-plugin/): local repository và install lifecycle.
- [Maven Deploy Plugin 3.1.4 — deploy:deploy](https://maven.apache.org/plugins-archives/maven-deploy-plugin-3.1.4/deploy-mojo.html): `deployAtEnd`, `altDeploymentRepository`, default false.
- [Maven Deploy Plugin — deploy:deploy](https://maven.apache.org/plugins/maven-deploy-plugin/deploy-mojo.html): các lưu ý non-atomic/partial upload ở documentation hiện hành.
- [Maven Deploy Plugin — Project Deployment](https://maven.apache.org/plugins/maven-deploy-plugin/usage.html): distributionManagement và remote repository.
- [Apache Maven — Settings Reference](https://maven.apache.org/settings.html): localRepository, server credentials, mirrors.
- [Maven Surefire Plugin — Using JUnit Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html): chạy JUnit Jupiter tests.
- [Maven Compiler Plugin — Setting --release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): target Java17.
