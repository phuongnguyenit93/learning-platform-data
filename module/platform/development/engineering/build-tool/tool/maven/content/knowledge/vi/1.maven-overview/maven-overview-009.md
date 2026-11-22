# Lộ trình học Maven: từ một dự án đơn giản đến hệ thống nhiều mô-đun

## 1. Mục tiêu và bức tranh tổng thể

Bài này hướng dẫn một đường học có thể thực hành từ đầu đến cuối: tạo dự án Java nhỏ bằng Apache Maven, hiểu cách Maven biên dịch, chạy kiểm thử và đóng gói, sau đó tách dự án thành các mô-đun có quan hệ phụ thuộc rõ ràng. Ví dụ dùng **JDK 17 trở lên, Maven 3.9.x, Java thuần và JUnit 5** để tập trung vào bản chất Maven; không cần Spring Boot hay máy chủ ứng dụng.

Sau lộ trình, bạn cần tự trả lời được: `pom.xml` mô tả gì; `mvn test` khác `mvn package` thế nào; dependency khác plugin ra sao; tại sao dự án nhiều mô-đun cần cả `<modules>`, `<parent>` và `<dependency>`; và cách chỉ build mô-đun cần thiết mà vẫn có đủ mô-đun phụ thuộc.

Một **Maven module** ở đây là một dự án con có `pom.xml` riêng. Nó không đồng nghĩa với Java Platform Module System (`module-info.java`), và cũng không tự động là một dịch vụ/microservice có thể triển khai độc lập.

## 2. Học theo các chặng có đầu ra kiểm chứng được

| Chặng | Học và thực hành | Dấu hiệu đã nắm vững |
| --- | --- | --- |
| 0. Chuẩn bị | Cài JDK, Maven; đọc cấu trúc `src/main` và `src/test` | `java -version` và `mvn -v` cho thấy Maven chạy bằng JDK phù hợp |
| 1. Dự án đơn | Tạo `pom.xml`, một lớp `main`, build JAR | `mvn package` thành công; chạy được chương trình |
| 2. Vòng đời build | Thực hành `compile`, `test`, `package`, `verify`, `install` | Giải thích được tác vụ nào chạy trước, `target/` chứa gì |
| 3. Thư viện và kiểm thử | Khai báo dependency JUnit, viết test, pin plugin | Một test đúng PASS, test sai khiến build FAIL |
| 4. Làm chủ POM | Hiểu coordinates, scopes, properties, plugins, effective POM | Biết đọc nguyên nhân thiếu dependency hoặc sai phiên bản |
| 5. Tách hai mô-đun | Chuyển logic dùng chung sang `core`, giữ điểm vào ở `app` | Reactor build `core` trước `app`; ứng dụng vẫn in cùng kết quả |
| 6. Quản lý toàn bộ build | Parent/aggregator, `dependencyManagement`, lệnh `-pl`/`-am` | Build từ gốc hoặc chọn riêng `app` đều thành công |
| 7. Mở rộng có kiểm soát | Tách thêm module khi có ranh giới rõ; kiểm tra CI và dependency graph | Không có phụ thuộc vòng, bản build tái lập được |

Nên hoàn thành sản phẩm của từng chặng trước khi chuyển chặng tiếp theo. Đừng tách hàng loạt mô-đun khi vẫn chưa hiểu và kiểm thử được một JAR đơn.

## 3. Chặng 0–1: Dựng một dự án Java duy nhất

### 3.1. Kiểm tra môi trường

Mở terminal và chạy:

~~~bash
java -version
javac -version
mvn -v
~~~

`mvn -v` phải cho thấy Java version và Java home tương ứng JDK bạn muốn dùng. Lệnh này hữu ích hơn việc chỉ nhìn `java -version`, vì Maven có thể được khởi chạy bằng một JDK khác qua `JAVA_HOME`. Khi mới học, chọn một JDK 17+ nhất quán.

Tạo cấu trúc thư mục:

~~~text
maven-journey/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/
                └── example/
                    └── app/
                        └── Main.java
~~~

Đây là bố cục mặc định của Maven: mã sản phẩm trong `src/main/java`, mã kiểm thử sau này trong `src/test/java`, tài nguyên trong `src/main/resources` và `src/test/resources`.

### 3.2. POM tối thiểu nhưng có phiên bản plugin rõ ràng

Nội dung `maven-journey/pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>app</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
        </plugins>
    </build>
</project>
~~~

Ý nghĩa của các phần quan trọng:

- `groupId:artifactId:version` là tọa độ xác định một artifact, ví dụ `vn.example:app:1.0.0`. `groupId` thường chỉ tổ chức; `artifactId` đặt tên sản phẩm; `version` là phiên bản sản phẩm.
- `packaging=jar` cho Maven biết cách đóng gói và gắn các plugin mặc định với vòng đời build.
- `maven.compiler.release=17` yêu cầu compiler tạo bytecode và chỉ cho phép API Java 17 trở xuống khi chạy bằng JDK phù hợp; đây không phải cách tự cài JDK 17.
- `project.build.sourceEncoding` giúp thống nhất cách biên dịch mã nguồn UTF-8.
- `maven-compiler-plugin` biên dịch Java, còn `maven-surefire-plugin` chạy unit test. Ghim phiên bản giúp tránh kết quả thay đổi theo mặc định của các bản Maven khác nhau. Phiên bản ví dụ là các bản phát hành cụ thể, không phải tuyên bố chúng luôn mới nhất.

### 3.3. Tạo điểm vào ứng dụng

Nội dung `src/main/java/vn/example/app/Main.java`:

~~~java
package vn.example.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Order A001: 250000 VND");
    }
}
~~~

Từ thư mục `maven-journey`, thực hiện:

~~~bash
mvn clean package
java -cp target/app-1.0.0.jar vn.example.app.Main
~~~

Kết quả của chương trình Java, sau khi Maven build thành công:

~~~text
Order A001: 250000 VND
~~~

Maven tạo `target/classes` chứa `.class` và `target/app-1.0.0.jar` chứa mã đã đóng gói. `java -cp ... Main` chạy được vì ví dụ chưa có thư viện runtime bên ngoài. Một JAR Maven thông thường không mặc nhiên có `Main-Class` trong manifest và không mặc nhiên nhúng các dependency; vì vậy **`java -jar` không phải lúc nào cũng chạy được**.

## 4. Chặng 2: Hiểu vòng đời Maven trước khi thêm độ phức tạp

Maven có **lifecycle**, mỗi lifecycle gồm các **phase**. Khi yêu cầu một phase, Maven đi qua những phase trước nó trong cùng lifecycle và gọi các **plugin goal** đã được gắn với chúng.

| Lệnh | Ý nghĩa thực tế |
| --- | --- |
| `mvn validate` | Kiểm tra cấu hình dự án ở phase validate |
| `mvn compile` | Biên dịch mã ứng dụng vào `target/classes` |
| `mvn test` | Biên dịch test và chạy unit test trong vòng đời mặc định |
| `mvn package` | Đi qua test rồi đóng gói artifact theo `packaging` |
| `mvn verify` | Đi qua package và chạy các kiểm tra được gắn tới verify |
| `mvn install` | Đi qua các phase trước, rồi đưa artifact vào local Maven repository |
| `mvn clean` | Chạy lifecycle `clean` để dọn sản phẩm build, thông thường là `target/` |
| `mvn clean verify` | Ghép lifecycle clean với việc build/kiểm tra tới verify |

Chú ý: `install` đưa artifact vào kho **cục bộ** (thường ở `~/.m2/repository`); nó không xuất bản lên Maven Central hoặc kho doanh nghiệp. Việc phát hành đến kho từ xa là một bước khác, thường liên quan phase `deploy` và cấu hình repository.

**Dependency** là thư viện hoặc artifact dự án cần để biên dịch, kiểm thử hay chạy. **Plugin** thực thi công việc build như compiler, test, packaging. Đừng nhầm phần `<dependencies>` với `<build><plugins>`.

Thử quan sát khác biệt: chạy `mvn clean compile` rồi kiểm tra `target/classes`; tiếp tục chạy `mvn package` để thấy file JAR. Nếu một test thất bại trong phase `test`, `package` bình thường sẽ không hoàn tất.

## 5. Chặng 3–4: Dependency, test và cách đọc POM

Maven thường lấy dependency từ repository đã cấu hình, lưu vào local repository rồi đưa lên classpath tùy phạm vi (`scope`). Một số scope cơ bản:

| Scope | Tác dụng cần nhớ |
| --- | --- |
| `compile` (mặc định) | Dùng khi biên dịch, kiểm thử và chạy; có thể truyền cho dự án phụ thuộc |
| `provided` | Cần cho biên dịch/test nhưng môi trường chạy dự kiến cung cấp; không phải dependency runtime thông thường |
| `runtime` | Không cần cho mã ứng dụng khi biên dịch, nhưng cần lúc chạy/test |
| `test` | Chỉ phục vụ biên dịch/chạy test, không là dependency runtime của artifact chính |

Ví dụ sau khi đã hiểu project đơn, thêm JUnit 5 vào POM trong `<project>`, ngang cấp `<build>`:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Có thể viết một phép tính nhỏ thành phương thức thuần, đặt test dưới `src/test/java`, rồi chạy `mvn test`. Test phải có khả năng **thất bại thật** khi kết quả sai; một build xanh nhưng không phát hiện test không có nhiều giá trị.

Khi gặp vấn đề dependency, hãy kiểm tra `groupId`, `artifactId`, `version`, `scope` và dependency bắc cầu (transitive). Các công cụ đọc cấu hình thường dùng:

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

`help:effective-pom` cho thấy POM sau khi tính kế thừa, cấu hình mặc định và profile liên quan; `dependency:tree` cho thấy cây phụ thuộc đã được Maven giải quyết. Với lần chạy đầu, Maven có thể tải plugin và thư viện qua mạng. Trong các dự án quan trọng, nên chọn phiên bản dependency/plugin có chủ đích và dùng Maven Wrapper nếu nhóm muốn thống nhất phiên bản Maven.

## 6. Chặng 5: Khi nào nên tách thành nhiều mô-đun?

Giả sử ứng dụng sau này cần tính tiền đơn hàng ở nhiều điểm vào (CLI, API, batch). Ta tách:

- `core`: quy tắc tính tiền thuần Java, kiểm thử độc lập, không phụ thuộc vào điểm vào ứng dụng.
- `app`: lớp `main` gọi `core` và quyết định cách hiển thị kết quả.
- `shop-parent`: POM tại thư mục gốc, điều phối build và tập trung cấu hình.

Ranh giới này đáng tách vì phần tính tiền có trách nhiệm riêng và có thể được tái sử dụng. Việc chỉ có nhiều package Java **không bắt buộc** phải tạo nhiều Maven module.

Từ ví dụ đơn ban đầu, chuyển `Main.java` vào `app/src/main/java/vn/example/app/`, cập nhật nó để gọi phép tính trong `core`, chuyển `pom.xml` gốc thành POM cha và tạo hai POM con. Cấu trúc kết quả:

~~~text
maven-journey/
├── pom.xml                            # shop-parent, packaging pom
├── core/
│   ├── pom.xml
│   └── src/
│       ├── main/java/vn/example/core/PriceCalculator.java
│       └── test/java/vn/example/core/PriceCalculatorTest.java
└── app/
    ├── pom.xml
    └── src/main/java/vn/example/app/Main.java
~~~

Ba quan hệ dưới đây **khác nhau** và cần hiểu tách bạch:

| Quan hệ | Khai báo ở đâu | Điều xảy ra |
| --- | --- | --- |
| **Aggregation** | `<modules>` trong POM gốc | Gộp các project vào một reactor build; không tự đưa mã module khác vào classpath |
| **Inheritance** | `<parent>` trong POM con | Kế thừa thông tin/cấu hình được Maven cho phép từ POM cha |
| **Dependency** | `<dependencies>` trong POM sử dụng thư viện | Xác lập yêu cầu artifact khác trên classpath, từ đó reactor biết thứ tự build liên quan |

Một POM vừa có thể là **parent** vừa là **aggregator**, như ví dụ dưới đây; ngoài thực tế hai vai trò cũng có thể nằm ở hai POM khác nhau.

### 6.1. POM gốc: `maven-journey/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>shop-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <junit.version>5.11.4</junit.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>${junit.version}</version>
            </dependency>
        </dependencies>
    </dependencyManagement>

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
        </plugins>
    </build>
</project>
~~~

`packaging=pom` phù hợp cho parent/aggregator: bản thân POM gốc không phải thư viện JAR của ứng dụng. Hai mục `<module>` là **đường dẫn tương đối tới thư mục có POM con**, không phải tọa độ artifact. Maven reactor đọc chúng rồi xác định thứ tự build dựa trên quan hệ thực tế.

`dependencyManagement` **quản lý phiên bản/quy tắc khi dependency được khai báo**, không tự thêm JUnit vào tất cả module. `<build><plugins>` ở POM cha trong ví dụ được các POM con kế thừa; khác với `pluginManagement` là nơi quản lý phiên bản/cấu hình plugin nhưng không tự làm mọi plugin hoạt động. Plugin đã gắn vào lifecycle mặc định vẫn có thể nhận cấu hình được quản lý.

### 6.2. POM thư viện: `core/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>shop-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

Vì POM `core` nằm dưới một cấp thư mục, Maven mặc định tìm POM cha tại `../pom.xml` thông qua `parent.relativePath`. `groupId` và `version` được kế thừa nên không cần lặp lại tại `core`. Phiên bản JUnit cũng được điền từ `dependencyManagement` ở cha, nhưng **chỉ `core` sử dụng JUnit vì chính `core` khai báo dependency đó**.

Nội dung `core/src/main/java/vn/example/core/PriceCalculator.java`:

~~~java
package vn.example.core;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static long total(long unitPrice, int quantity) {
        if (unitPrice < 0 || quantity < 0) {
            throw new IllegalArgumentException("Inputs must be non-negative");
        }
        return Math.multiplyExact(unitPrice, quantity);
    }
}
~~~

`Math.multiplyExact` báo `ArithmeticException` nếu phép nhân vượt phạm vi `long`; ví dụ tránh âm nhưng chưa phải mô hình tiền tệ hoàn chỉnh. Với tiền thật, cần quyết định rõ đơn vị nhỏ nhất, làm tròn, thuế/giảm giá và giới hạn số lượng.

Nội dung `core/src/test/java/vn/example/core/PriceCalculatorTest.java`:

~~~java
package vn.example.core;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PriceCalculatorTest {
    @Test
    void calculatesTotal() {
        assertEquals(250_000L, PriceCalculator.total(125_000L, 2));
    }

    @Test
    void rejectsNegativeQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> PriceCalculator.total(100L, -1));
    }
}
~~~

Hai test kiểm tra một kết quả đúng và một trường hợp đầu vào không hợp lệ. Các test dùng JUnit 5 được Surefire chạy trong phase `test`; nếu sửa kết quả kỳ vọng thành sai, build phải thất bại.

### 6.3. POM ứng dụng: `app/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>vn.example</groupId>
        <artifactId>shop-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>vn.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>
    </dependencies>
</project>
~~~

Quan hệ `app → core` xuất hiện nhờ `<dependency>`, không phải chỉ vì hai thư mục cùng xuất hiện trong `<modules>`. `${project.version}` ở đây bằng `1.0.0` do `app` kế thừa phiên bản từ POM cha; đây là cách đơn giản để ví dụ luôn dùng cùng phiên bản reactor.

Nội dung `app/src/main/java/vn/example/app/Main.java`:

~~~java
package vn.example.app;

import vn.example.core.PriceCalculator;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        long amount = PriceCalculator.total(125_000L, 2);
        System.out.println("Order A001: " + amount + " VND");
    }
}
~~~

Hãy chú ý đường đi của mã: `Main` chỉ biết API công khai của `core`; `core` không biết lớp `Main` và không phụ thuộc ngược vào `app`.

### 6.4. Build, test và chạy sản phẩm nhiều mô-đun

Từ thư mục gốc `maven-journey`:

~~~bash
mvn clean verify
~~~

Khi thành công, reactor thường hiển thị thứ tự tương ứng `shop-parent`, `core`, `app` và tổng kết `SUCCESS`; thứ tự chính xác dựa vào quan hệ giữa các project. Vì `app` phụ thuộc `core`, reactor cần build `core` trước `app`, kể cả khi bạn đổi thứ tự hai tên trong `<modules>`.

Kiểm tra artifact:

~~~text
core/target/core-1.0.0.jar
app/target/app-1.0.0.jar
~~~

Để chạy Java thuần với **hai JAR riêng biệt**, phải đưa cả hai lên classpath. Trên Windows PowerShell hoặc CMD (dấu phân cách là dấu chấm phẩy):

~~~bash
java -cp "app/target/app-1.0.0.jar;core/target/core-1.0.0.jar" vn.example.app.Main
~~~

Trên Linux/macOS (dấu phân cách là dấu hai chấm):

~~~bash
java -cp "app/target/app-1.0.0.jar:core/target/core-1.0.0.jar" vn.example.app.Main
~~~

Đầu ra kỳ vọng ở cả hai hệ:

~~~text
Order A001: 250000 VND
~~~

Đây là **JAR thông thường**. Nếu cần một JAR tự chứa tất cả thư viện hoặc chạy `java -jar`, bạn phải cấu hình manifest và cách đóng gói tương ứng (chẳng hạn Shade Plugin cho trường hợp phù hợp); Maven không tự tạo executable/fat JAR chỉ nhờ `<modules>`.

## 7. Chặng 6: Chọn đúng phần của reactor để build

Tại thư mục gốc, Maven hỗ trợ chọn một phần reactor:

~~~bash
mvn -pl :core test
mvn -pl :app -am package
mvn -pl :core -amd test
mvn -rf :app package
~~~

Đọc từng lệnh:

- `-pl :core` (hoặc `--projects :core`): chọn artifactId `core`.
- `-pl :app -am` (hoặc `--also-make`): chọn `app` và cả các project trong reactor mà `app` cần; lựa chọn thường dùng cho build tăng dần.
- `-pl :core -amd` (hoặc `--also-make-dependents`): chọn `core` cùng các project trong reactor phụ thuộc vào nó; phù hợp đánh giá tác động của thay đổi thư viện.
- `-rf :app` (hoặc `--resume-from`): tiếp tục reactor từ `app` sau một lần build dừng; **không mặc nhiên build lại mọi dependency phía trước**.

Các cờ này tác động đến **project nào được build trong reactor**; chúng không tự sửa quan hệ dependency. Thử nghiệm từ checkout sạch: chạy `mvn -pl :app package` **không có `-am`** có thể không tìm thấy `core` nếu artifact đó chưa có trong local/remote repository. Dùng `-am` hoặc build đầy đủ từ gốc để Maven đưa `core` vào reactor lần ấy.

Cách kiểm tra cấu hình và cây phụ thuộc sau khi tách:

~~~bash
mvn -pl :app help:effective-pom
mvn -pl :app -am dependency:tree
~~~

Lệnh `dependency:tree` liệt kê quan hệ dependency; bạn phải nhìn thấy `app` dùng `vn.example:core:1.0.0`. Lệnh `effective-pom` giúp kiểm tra `app` đã nhận phiên bản Java/plugin từ cha và phiên bản dependency do quản lý hay chưa. Trên CI, nên chạy ít nhất một build toàn reactor để bảo đảm các module phối hợp tốt.

## 8. Chặng 7: Mở rộng từ hai module thành hệ thống dễ bảo trì

Chỉ tách thêm mô-đun khi có **lý do thiết kế rõ**: trách nhiệm riêng, API giao tiếp đủ ổn định, nhu cầu tái sử dụng hoặc nhịp kiểm thử/phát hành khác nhau. Ví dụ có thể phát triển thành `domain` (quy tắc nghiệp vụ), `persistence` (lưu trữ), `cli` (điểm vào lệnh), `api` (điểm vào HTTP) nếu thực tế cần; không tạo sẵn mọi module chỉ vì một dự án lớn trong tương lai.

Các nguyên tắc đáng giữ khi hệ thống tăng trưởng:

1. **Hướng phụ thuộc một chiều.** Phần lõi nghiệp vụ không import điểm vào; không tạo chu trình `core → app → core`. Maven reactor không giải quyết được phụ thuộc vòng.
2. **Đặt cấu hình chung ở cha.** Tập trung Java release, encoding, phiên bản test/plugin; có thể dùng `pluginManagement` để quản lý plugin mà các module chủ động khai báo hoặc dùng qua lifecycle. Đừng lặp phiên bản tùy tiện ở từng module.
3. **Phân biệt “quản lý” và “sử dụng”.** `dependencyManagement` quản lý cách phiên bản được chọn; `dependencies` mới khiến dependency xuất hiện. Nếu dùng BOM, import POM trong `dependencyManagement` với `type=pom` và `scope=import`, sau khi hiểu lý do cần BOM.
4. **Giữ test gần mã sở hữu.** Unit test của `core` nằm trong `core`; test tích hợp đi qua nhiều module cần môi trường và cấu hình tách biệt phù hợp. Đừng chỉ dựa vào việc Maven báo `BUILD SUCCESS` nếu không kiểm tra số test đã chạy.
5. **Ghim công cụ để dễ tái lập.** Ấn định phiên bản plugin, JDK hỗ trợ và phiên bản Maven cho CI/nhóm; dùng Maven Wrapper khi phù hợp. Cân nhắc kiểm tra `dependency:tree` định kỳ để phát hiện dependency bắc cầu xung đột.
6. **Kiểm soát mức độ chia nhỏ.** Mỗi module làm tăng POM, phụ thuộc và phạm vi build cần duy trì. Nhiều module có ích khi ranh giới có thật, không phải chỉ vì nhiều thư mục.

## 9. Lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Cần kiểm tra trước |
| --- | --- |
| `invalid target release: 17` hoặc lỗi Java release | `mvn -v` đang chạy bằng JDK nào; `JAVA_HOME` và `maven.compiler.release` có tương thích không |
| `package ... does not exist` khi `app` import `core` | Đã khai báo `core` trong `app/dependencies`, đúng tọa độ, package Java và build cùng reactor với `-am` chưa |
| `Could not find artifact vn.example:core` | Đang chọn `app` đơn lẻ khi `core` chưa được build/install; chạy từ gốc với `-am` hoặc build toàn reactor |
| Không tìm thấy POM cha | `<parent>` sai tọa độ/version; vị trí `../pom.xml` hoặc `relativePath` sai |
| Test JUnit không được chạy | Tên/đường dẫn test đúng quy ước; `junit-jupiter` scope test; phiên bản Surefire hỗ trợ JUnit Platform |
| `NoClassDefFoundError` lúc chạy app | Đã có dependency trên runtime classpath chưa; JAR thông thường không gộp dependency |
| `no main manifest attribute` khi `java -jar` | Chưa cấu hình manifest entry point; cân nhắc cách đóng gói ứng dụng |
| Phiên bản dependency khác mong đợi | Dùng `help:effective-pom` và `dependency:tree` để xem kế thừa, quản lý phiên bản và cây transitive |
| Reactor báo cyclic reference | Các module phụ thuộc vòng; cần chỉnh lại hướng phụ thuộc, không thể sửa chỉ bằng sắp lại `<modules>` |

Để chẩn đoán, đọc **thông báo lỗi đầu tiên có ý nghĩa** và module nào vừa thất bại trong `Reactor Summary`. Đừng chữa lỗi phụ thuộc bằng cách thêm ngẫu nhiên JAR vào thư mục, cũng đừng bỏ qua toàn bộ test chỉ để có bản build xanh.

## 10. Bài tập cuối lộ trình và tiêu chí tự kiểm tra

**Bài tập A — giữ dự án đơn hoạt động:** Từ cấu trúc đầu bài, tự viết POM và lớp `Main`, chạy `mvn clean package` rồi `java -cp ... Main`. Giải thích được artifact có tọa độ gì và vì sao Maven đặt nó vào `target/`.

**Bài tập B — thấy test bảo vệ hành vi:** Tạo hàm tính tổng bằng phép nhân an toàn, thêm JUnit test cho đầu vào hợp lệ và không hợp lệ. Cố ý đổi một phép so sánh trong test để quan sát phase `test` làm build thất bại, rồi khôi phục test.

**Bài tập C — tách module không đổi hành vi:** Chuyển hàm tính toán vào `core`, ứng dụng sang `app` và cấu hình parent như phần 6. Hai JAR phải được tạo, test của `core` phải PASS, đầu ra `Main` vẫn là `Order A001: 250000 VND`.

**Bài tập D — hiểu quan hệ:** Tạm bỏ dependency `core` khỏi `app/pom.xml` rồi chạy build để quan sát lỗi compile; khôi phục dependency. So sánh với việc chỉ để `core` trong `<modules>`. Từ đây hãy giải thích vì sao aggregation không thay thế dependency.

**Bài tập E — build có chọn lọc:** Thử `mvn -pl :app -am package` từ root; sau đó giải thích tại sao `-am` quan trọng khi `core` chưa có trong repository. Kiểm tra `help:effective-pom` và `dependency:tree` để chứng minh plugin và dependency đang được dùng đúng.

Đạt lộ trình khi bạn **tự tạo và chạy được** cả bản một module lẫn bản hai module; đọc được POM cha/con; lý giải được thứ tự reactor; phân biệt inheritance, aggregation, dependency; và chỉ ra được cách kiểm tra khi một lệnh Maven build thất bại. Bắt đầu từ hệ thống chạy được, sau đó mới tăng số module là cách học dễ kiểm chứng nhất.

## 11. Tài liệu Maven chính thức để tra cứu thêm

- [Maven in 5 Minutes](https://maven.apache.org/guides/getting-started/maven-in-five-minutes.html): dự án Maven đơn, vòng đời cơ bản và cấu trúc.
- [POM Reference](https://maven.apache.org/pom.html): cấu trúc POM, kế thừa, aggregation và quản lý dependency.
- [Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): cơ chế reactor và các cờ `-pl`, `-am`, `-amd`, `-rf` trong Maven 3.
- [Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism): scope, dependency bắc cầu và dependency management.
- [Compiler Plugin — Setting the Release](https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-release.html): ý nghĩa cấu hình `maven.compiler.release`.
