# Phân biệt `mvn clean verify` với việc gọi riêng một plugin goal

## 1. Vấn đề: cùng là lệnh Maven, nhưng phạm vi thực thi khác nhau

Khi làm việc với Maven, bạn sẽ gặp hai nhóm lệnh:

```bash
mvn clean verify
mvn compiler:compile
```

Cả hai đều do Maven điều phối, nhưng ý nghĩa khác nhau:

- **`mvn clean verify`** gọi **các phase của lifecycle**: chạy phase `clean` thuộc clean lifecycle, rồi chạy default lifecycle đến phase `verify`. Maven thực hiện các phase trước đó theo thứ tự và các **plugin goal** đã được gắn vào từng phase.
- **`mvn compiler:compile`** gọi **trực tiếp một goal** của Maven Compiler Plugin. Lệnh này yêu cầu goal `compile` của plugin, chứ không tự có nghĩa chạy toàn bộ default lifecycle đến phase `compile`.

Phân biệt này giải thích vì sao một câu lệnh có thể build sạch, chạy kiểm thử, tạo JAR và kiểm tra chất lượng, còn một câu lệnh khác chỉ thử biên dịch mã nguồn hoặc làm một tác vụ chuyên biệt.

## 2. Ba khái niệm: lifecycle, phase và plugin goal

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Lifecycle** | `clean`, `default`, `site` | Chuỗi phase có thứ tự được Maven định nghĩa |
| **Phase** | `compile`, `test`, `package`, `verify` | Mốc công việc trong lifecycle; gọi phase thì Maven đi qua các phase đứng trước nó trong cùng lifecycle |
| **Plugin goal** | `compiler:compile`, `surefire:test`, `jar:jar` | Một hành động cụ thể do plugin triển khai |

Một phase có thể có **không, một hoặc nhiều goal** được gắn. Nếu phase không có goal nào, nó vẫn là một mốc trong thứ tự lifecycle nhưng không phát sinh tác vụ ở phase ấy. Packaging của project (ví dụ `jar` hoặc `war`) và cấu hình `<executions>` trong POM quyết định các binding.

Ví dụ với dự án Maven đóng gói `jar` thông thường:

| Phase trong default lifecycle | Goal thường được gắn |
| --- | --- |
| `process-resources` | `resources:resources` |
| `compile` | `compiler:compile` |
| `process-test-resources` | `resources:testResources` |
| `test-compile` | `compiler:testCompile` |
| `test` | `surefire:test` |
| `package` | `jar:jar` |

Plugin goal chính là thứ thực hiện tác vụ thực tế; lifecycle quyết định **khi nào và theo thứ tự nào** các tác vụ ấy chạy.

## 3. `mvn clean verify` thực hiện những gì?

Maven có ba lifecycle dựng sẵn: `clean`, `default` và `site`. `mvn clean verify` yêu cầu hai phase từ hai lifecycle khác nhau trong **một invocation**.

### Bước 1: chạy clean lifecycle đến phase `clean`

Clean lifecycle gồm `pre-clean`, `clean` và `post-clean`. Khi yêu cầu `clean`, Maven đi qua `pre-clean` và `clean`, trong đó goal mặc định thường là `clean:clean` ở phase `clean`.

Clean Plugin thường dọn `target` của các project trong phạm vi build. Nó không xóa source `src/main/java` hoặc POM. Nếu cấu hình plugin dọn bổ sung, cần kiểm tra kỹ phạm vi file đích; bài này nói về hành vi thông thường.

**Lưu ý:** gọi phase `clean` không tự đi tiếp đến phase `post-clean`, vì phase đó **đứng sau `clean`** trong cùng lifecycle.

### Bước 2: chạy default lifecycle đến phase `verify`

Maven tiếp tục default lifecycle, lần lượt đi qua những phase đứng trước hoặc bằng `verify`:

```text
validate
  ↓
initialize
  ↓
generate-sources / process-sources
  ↓
generate-resources / process-resources
  ↓
compile
  ↓
generate-test-sources / process-test-sources
  ↓
generate-test-resources / process-test-resources
  ↓
test-compile
  ↓
test
  ↓
prepare-package / package
  ↓
pre-integration-test → integration-test → post-integration-test
  ↓
verify
```

Đây là sơ đồ đã lược bớt một số phase trung gian; danh sách phase đầy đủ nằm trong tài liệu Maven. Tại mỗi phase, Maven chạy các goal **thực sự được bind** theo packaging và cấu hình project. Không phải phase nào cũng tự có một công việc.

Trong project JAR bình thường, các bước đáng quan sát là:

1. Maven xử lý tài nguyên chính rồi biên dịch Java main.
2. Maven xử lý tài nguyên test, biên dịch test và thường chạy unit test qua Surefire.
3. Maven đóng gói JAR từ class/resource main.
4. Maven chạy các kiểm tra bổ sung ở những phase đến `verify` **nếu project đã cấu hình** những goal đó.

Điều này có hai hệ quả quan trọng:

- `mvn clean verify` **thường đã tạo JAR** ở phase `package` trước khi kết thúc ở `verify`.
- **Không mặc định có integration test hoặc kiểm tra chất lượng chuyên biệt** chỉ vì câu lệnh chứa `verify`. Các công việc đó cần plugin/goal/execution được cấu hình; ví dụ Failsafe thường sử dụng các phase `integration-test` và `verify`.

`verify` đứng **trước** `install` và `deploy`. Vì vậy `mvn clean verify` không tự cài artifact vào local repository bằng `install:install` hay đẩy artifact lên remote repository bằng `deploy:deploy`.

### Vì sao dùng `clean`?

`mvn verify` không tự xóa output từ build trước. `mvn clean verify` giúp loại bỏ nhiều class/JAR/report cũ để thử build từ trạng thái sạch. Nó đặc biệt hữu ích khi generator, compiler, test hoặc packaging vô tình dựa vào file trong `target` còn sót lại. Tuy nhiên build lặp lại hoàn toàn còn phụ thuộc JDK, dependency/plugin versions, input và môi trường.

## 4. Gọi trực tiếp plugin goal có gì khác?

Cú pháp:

```text
mvn <plugin-prefix>:<goal>
```

Ví dụ:

```bash
mvn compiler:compile
mvn surefire:test
mvn jar:jar
mvn dependency:tree
mvn clean:clean
```

Maven phân giải plugin prefix thành một plugin cụ thể, tải plugin nếu cần, rồi thực thi goal tương ứng. Goal có thể yêu cầu resolve dependencies hoặc làm một số thao tác nội bộ, nhưng **một lời gọi goal trực tiếp thông thường không tự yêu cầu Maven chạy mọi phase trước đó**.

Vì vậy:

- `mvn compiler:compile` yêu cầu Compiler Plugin biên dịch mã chính trong điều kiện hiện có; nó **không bảo đảm** đã chạy generator ở `generate-sources` hoặc resource processing trước đó.
- `mvn surefire:test` yêu cầu Surefire chạy các test đã được chuẩn bị; nó **không tự đồng nghĩa** compile source và test source từ đầu.
- `mvn jar:jar` gọi JAR Plugin để đóng gói từ output hiện có; nó **không bảo đảm** các class/resource trong `target/classes` đã được tái tạo từ source mới.
- `mvn dependency:tree` xem đồ thị dependency; không phải một build tuần tự đến `test` hay `package`.
- `mvn clean:clean` gọi trực tiếp goal của Clean Plugin. Trong project đơn giản nó có thể dọn `target` giống phần việc chính của phase `clean`, nhưng nó **không đồng nghĩa toàn bộ clean lifecycle** khi có goal gắn ở `pre-clean` hoặc các phase liên quan.

**Ngoại lệ kỹ thuật:** một số plugin goal có khả năng *fork lifecycle* hoặc thực hiện yêu cầu đặc biệt. Vì vậy tránh khẳng định rằng không có goal nào có thể làm việc ngoài chính nó. Khi nghi ngờ, tra tài liệu goal và effective POM. Quy tắc để lập kế hoạch build vẫn là: dùng **phase** khi muốn đi qua lifecycle; dùng **goal** khi cần một tác vụ cụ thể.

## 5. So sánh các lệnh hay gặp

| Lệnh | Clean output cũ? | Chạy các phase mặc định trước mốc cuối? | Ý định chính |
| --- | --- | --- | --- |
| `mvn clean verify` | Có, thông thường | Có, default đến `verify` | Build sạch + kiểm chứng theo cấu hình |
| `mvn verify` | Không tự clean | Có, default đến `verify` | Build/kiểm chứng với output đang có |
| `mvn clean package` | Có, thông thường | Có, default đến `package` | Build sạch và đóng gói |
| `mvn test` | Không tự clean | Có, default đến `test` | Build đủ để chạy unit test |
| `mvn compiler:compile` | Không | Không tự chạy toàn bộ lifecycle | Gọi goal biên dịch mã chính |
| `mvn clean compiler:compile` | Có vì gọi phase `clean` | Không tự chạy default lifecycle | Dọn output rồi gọi trực tiếp compiler goal |
| `mvn surefire:test` | Không | Không tự chạy toàn bộ lifecycle | Gọi test runner trực tiếp |
| `mvn jar:jar` | Không | Không tự chạy toàn bộ lifecycle | Đóng JAR từ input/output mà goal sử dụng |
| `mvn clean:clean` | Goal này dọn theo cấu hình | Không tự chạy toàn bộ clean lifecycle | Chỉ gọi goal của Clean Plugin |
| `mvn dependency:tree` | Không | Không | Phân tích dependency graph |

“Có clean” trong bảng nghĩa là clean phase/goal đã được yêu cầu; việc xóa cụ thể phụ thuộc cấu hình Clean Plugin. Các goal có thể có yêu cầu và hành vi riêng, nhưng **không nên suy ra** chúng tương đương full lifecycle.

### `clean:clean` có giống `clean` không?

- `clean` là **phase** của clean lifecycle; Maven chạy các phase đứng trước nó và các goal được gắn.
- `clean:clean` là **goal** của Clean Plugin, gọi trực tiếp.
- Trong project có binding mặc định, phần hành vi dọn output có thể giống nhau; nếu có logic gắn ở `pre-clean` thì chỉ gọi `clean:clean` có thể bỏ qua logic ấy.

### `compiler:compile` có giống `compile` không?

- `compile` là **phase** của default lifecycle, nên đi qua `generate-sources`, `process-resources` và các phase trước đó.
- `compiler:compile` là **goal**, chỉ thực hiện nhiệm vụ của Compiler Plugin theo input/config có sẵn.
- Nếu project tạo Java source ở `generate-sources`, `mvn compile` có thể thành công còn `mvn compiler:compile` từ build sạch có thể báo thiếu generated class do generator chưa chạy.

### `surefire:test` có giống `test` không?

- `test` là **phase**, đi qua compile main/test và các phase xử lý tài nguyên.
- `surefire:test` là **goal**, thường sử dụng test classes đã có. Nếu test chưa được biên dịch, nó có thể không chạy như bạn kỳ vọng hoặc báo lỗi theo cấu hình.
- Muốn tin cậy rằng test phản ánh source mới nhất, thường chạy `mvn test` hoặc `mvn clean test`.

## 6. Ví dụ thực hành Java 17: từ build sạch đến kiểm thử và JAR

Tạo dự án với ba file:

```text
lifecycle-demo/
├── pom.xml
└── src/
    ├── main/java/demo/App.java
    └── test/java/demo/AppTest.java
```

**File `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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
    </build>
</project>
```

**File `src/main/java/demo/App.java`:**

```java
package demo;

public final class App {
    private App() {
    }

    public static String message() {
        return "Lifecycle ready";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**File `src/test/java/demo/AppTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void messageIsStable() {
        assertEquals("Lifecycle ready", App.message());
    }
}
```

Cần JDK 17+, Maven tương thích và repository truy cập được khi phải tải plugin/dependency lần đầu.

### 6.1. Chạy full lifecycle

Trong thư mục `lifecycle-demo/` có `pom.xml`:

```bash
mvn clean verify
java -cp target/lifecycle-demo-1.0.0.jar demo.App
```

Dòng **stdout chính xác** từ chương trình Java:

```text
Lifecycle ready
```

Sau build thành công, các file quan trọng thường gồm:

```text
target/
├── classes/demo/App.class
├── test-classes/demo/AppTest.class
├── surefire-reports/...
└── lifecycle-demo-1.0.0.jar
```

Thứ tự hợp lý trong log Maven: Clean Plugin xóa đầu ra cũ; Resources Plugin xử lý resources; Compiler Plugin compile main và test; Surefire chạy unit test; JAR Plugin đóng gói; Maven đến phase verify rồi kết thúc nếu không có goal bổ sung hoặc chạy goal verify đã cấu hình.

Với POM trên, **không có integration test plugin riêng**. Đến `verify` không có nghĩa đã tự sinh hay chạy integration test. Nếu JUnit assertion sai, mặc định build thường dừng trước khi kết thúc thành công, bởi unit test là một phần của chuỗi phase trước `verify`.

### 6.2. Đối chiếu với goal riêng

Sau khi `mvn clean verify` đã thành công, thử:

```bash
mvn compiler:compile
mvn surefire:test
mvn jar:jar
```

Các goal có thể sử dụng output đã tồn tại trong `target` nên có vẻ “tương đương” full build trong dự án đơn giản. Nhưng điều đó **không chứng minh** chúng đã tự chạy toàn bộ các phase trước đó.

Thử tạo trạng thái sạch rồi gọi goal trực tiếp:

```bash
mvn clean
mvn compiler:compile
```

Lúc này compiler goal được gọi, có thể tạo `target/classes/demo/App.class`, nhưng không tự chạy `test-compile`, `surefire:test` và `jar:jar`. Vì thế chưa có lý do để kết luận unit test đã chạy hoặc artifact JAR hiện tại đã được tạo.

Nếu bạn chỉ chạy:

```bash
mvn clean
mvn jar:jar
```

JAR Plugin có thể tạo output dựa trên những class/resource đang có hoặc thể hiện hành vi khác theo cấu hình, nhưng **không tự đảm bảo** chạy bước biên dịch source mới. Cần xem artifact thực tế; không suy luận JAR hợp lệ về nghiệp vụ chỉ vì lệnh tạo file `.jar` không lỗi.

## 7. Vấn đề dữ liệu cũ: vì sao một goal có thể đánh lừa?

Giả sử thứ Hai bạn chạy `mvn clean verify` và có `target/classes`, `target/test-classes`. Thứ Ba bạn sửa một lớp Java hoặc unit test, rồi chỉ chạy `mvn surefire:test`.

Trong tình huống thường gặp, Surefire dùng các class test đã compile từ thứ Hai. Kết quả test PASS khi ấy **có thể kiểm tra bytecode cũ**, không phản ánh thay đổi source mới. Tương tự `jar:jar` có thể đóng gói các class cũ nếu chưa compile lại.

Cách làm phù hợp:

- Muốn build và chạy unit test theo source hiện tại: `mvn test`; nếu nghi output còn sót, `mvn clean test`.
- Muốn build sạch và kiểm chứng thêm các goal đã cấu hình đến verify: `mvn clean verify`.
- Muốn phân tích dependency mà không cần đóng gói: `mvn dependency:tree`.
- Muốn xem cấu hình Maven đã kế thừa: `mvn help:effective-pom`.
- Muốn làm một tác vụ plugin chuyên biệt: gọi goal trực tiếp, nhưng xác định trước các input/prerequisite goal cần.

Đừng lạm dụng việc gọi riêng `compiler:compile`, `surefire:test`, `jar:jar` theo chuỗi thủ công để mô phỏng lifecycle: dễ quên `generate-sources`, resource processing, các checks và các execution custom. Maven lifecycle được thiết kế để quản lý thứ tự cho bạn.

## 8. Gắn thêm plugin goal vào lifecycle

Giả sử dự án cần một goal tạo mã từ schema trước khi compile. Một plugin generator có thể được bind vào phase `generate-sources` bằng `<executions>`. Ví dụ **minh họa cấu trúc binding** (không phải plugin/goal có thể chạy độc lập):

```xml
<plugin>
    <groupId>example.tools</groupId>
    <artifactId>example-codegen-maven-plugin</artifactId>
    <version>1.2.3</version>
    <executions>
        <execution>
            <id>generate-model</id>
            <phase>generate-sources</phase>
            <goals>
                <goal>generate</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Trong project thực phải dùng tọa độ, goal và cấu hình **có thật** của generator đang chọn. Ý nghĩa cú pháp là gắn goal `generate` vào phase `generate-sources`, để `mvn compile` hoặc `mvn verify` đi qua phase đó và tạo source trước khi compile.

Nếu bạn chỉ gọi `mvn compiler:compile`, binding ở `generate-sources` thông thường không chạy. Đây là khác biệt quan trọng khi kết nối code generation, schema validation, static analysis và kiểm thử vào lifecycle.

Một ví dụ plugin có thật về integration test là Maven Failsafe Plugin: khi cấu hình phù hợp, goal `failsafe:integration-test` thường được gắn vào `integration-test` và `failsafe:verify` vào `verify`. Khi đó `mvn verify` cho phép các bước trước/sau integration test chạy theo thứ tự. Gọi riêng `mvn failsafe:integration-test` có thể không thực hiện toàn bộ setup/teardown hay bước xác nhận kết quả mong muốn; theo tài liệu Maven, không nên chọn phase `integration-test` làm đích thay cho `verify` nếu cần chuỗi trọn vẹn.

## 9. Gọi nhiều phase và goal trong cùng một invocation

Lệnh Maven có thể trộn phase với goal:

```bash
mvn clean dependency:tree package
```

Theo thứ tự trên, Maven chạy clean lifecycle đến `clean`, gọi trực tiếp goal `dependency:tree`, rồi chạy default lifecycle đến `package`. Goal `dependency:tree` không biến thành một phase và cũng không làm `package` biến mất.

Một ví dụ khác:

```bash
mvn clean compiler:compile
```

Maven chạy phase `clean`, rồi gọi **goal `compiler:compile` trực tiếp**. Phần sau không có nghĩa chạy default lifecycle đến phase `compile`; vì thế có thể bỏ qua goal generator hoặc resource processing đã bind ở các phase trước.

Nếu project đã bind goal compiler vào lifecycle, gọi thêm `compiler:compile` bằng tay **sau `mvn compile`** có thể khiến goal compiler được yêu cầu thêm lần nữa; cần tránh gọi lặp vô ích. Maven có thể tối ưu/không compile lại theo trạng thái hiện có, nhưng không nên dùng đó làm lý do tạo chuỗi goal không rõ mục đích.

## 10. Các giới hạn của `mvn clean verify`

**`verify` không đồng nghĩa “đã chạy mọi kiểu test”.** Điều gì chạy phụ thuộc POM, plugin, packaging, profile và các skip flags. Với Maven JAR thông thường, unit test thường qua Surefire; integration tests cần cấu hình bổ sung.

**`clean` không đảm bảo build tái lập tuyệt đối.** Dù xóa `target`, cùng version `-SNAPSHOT` có thể resolve ra artifact khác; JDK, plugin version, environment variable, system locale hoặc repository mirror khác vẫn có thể ảnh hưởng.

**`verify` không cài hoặc phát hành artifact.** `install` nằm sau `verify` và cài vào local repository; `deploy` nằm sau `install` và triển khai đến remote repository đã cấu hình. Chỉ chạy `mvn clean verify` chưa tương đương phát hành.

**Mục tiêu build có thể bị thay đổi bởi skip flags.** Ví dụ `-DskipTests` thường bỏ chạy unit tests trong Surefire, còn `-Dmaven.test.skip=true` có thể bỏ cả compile test và chạy test. Đọc lại effective config trước khi xem build PASS là bằng chứng kiểm thử.

**Goal trực tiếp cũng có cấu hình.** Plugin có thể được quản lý bằng `<pluginManagement>` hoặc khai trong `<build><plugins>`; nếu chưa pin version, Maven có thể dùng version được resolve theo cấu hình hiện có. Đối với CI, pin các phiên bản plugin quan trọng để giảm bất ngờ.

## 11. Khi nào chọn phase, khi nào chọn goal?

| Mục đích | Lệnh thường phù hợp | Lý do |
| --- | --- | --- |
| Build sạch, chạy unit test, đóng gói và kiểm tra bổ sung | `mvn clean verify` | Lifecycle đảm bảo thứ tự các phase được định nghĩa |
| Build nhanh đến unit test, không cần đóng gói | `mvn test` | Dừng ở phase `test` |
| Build JAR/WAR theo cấu hình | `mvn package` hoặc `mvn clean package` | Đi qua các bước trước `package` |
| Kiểm tra dependency graph | `mvn dependency:tree` | Mục tiêu là phân tích, không build artifact |
| Xem effective POM | `mvn help:effective-pom` | Mục tiêu là quan sát cấu hình |
| Thử một goal chuyên biệt khi các prerequisite đã sẵn sàng | `mvn plugin:goal` | Chủ động gọi thao tác của plugin |
| Đưa artifact vào local repository | `mvn install` | Bao gồm default lifecycle đến `install` |
| Phát hành lên remote repository đã cấu hình | `mvn deploy` | Bao gồm default lifecycle đến `deploy` |

Trước khi dùng plugin goal riêng, hãy hỏi: goal có yêu cầu source đã generate, class đã compile, test class đã có hay package đã tạo không? Nếu có, hãy gọi phase phù hợp trước hoặc ràng buộc goal vào lifecycle.

## 12. Những nhầm lẫn thường gặp

**“`verify` chỉ chạy một goal tên verify.”** Sai. `verify` là phase của default lifecycle; nó kéo theo các phase trước đó, còn goal nào chạy ở mỗi phase phụ thuộc binding.

**“`clean verify` nghĩa là hai plugin goal.”** Sai. `clean` và `verify` trong câu lệnh này là tên hai phase. `clean:clean`, `compiler:compile`, `surefire:test` và `jar:jar` mới là biểu diễn plugin goal.

**“`compiler:compile` luôn tương đương `mvn compile`.”** Sai. Trong project đơn giản hai lệnh có thể đều tạo class main; nhưng gọi phase `compile` bảo đảm đi qua những phase trước nó và goal có binding, còn gọi goal trực tiếp không mặc định làm việc ấy.

**“`surefire:test` PASS chắc chắn source mới đã được biên dịch.”** Sai. Goal này có thể chạy trên test classes đang có. Muốn bảo đảm build/test từ đầu ra mới, chọn `mvn clean test` hoặc `mvn clean verify` theo nhu cầu.

**“`jar:jar` luôn tạo JAR production mới từ source mới.”** Sai. JAR Plugin đóng gói theo input hiện có; nó không tự thay thế quy trình compile/test.

**“`mvn clean verify` chạy integration tests trong mọi dự án.”** Sai. Integration tests chỉ chạy nếu có công cụ và binding phù hợp, chẳng hạn Failsafe.

**“`mvn verify` cũng clean như `mvn clean verify`.”** Sai. `verify` chỉ thuộc default lifecycle; clean là lifecycle riêng và cần được gọi khi muốn dọn output theo cấu hình.

## 13. Checklist trước khi chạy lệnh Maven trong CI

- [ ] Biết đang chọn POM nào và project có packaging gì.
- [ ] Biết mục tiêu là phase của lifecycle hay plugin goal trực tiếp.
- [ ] Có cần clean để tránh output cũ không.
- [ ] Kiểm tra code generation, resources, compile và test có execution/binding đúng phase.
- [ ] Nếu muốn integration tests, kiểm tra Failsafe hoặc runner tương ứng đã được cấu hình.
- [ ] Pin phiên bản plugin quan trọng và kiểm soát dependency versions/profiles.
- [ ] Không dùng goal đơn lẻ thay full build chỉ vì nó chạy nhanh sau một lần build cũ.
- [ ] Xác định có thực sự cần `install` hoặc `deploy` hay chỉ cần `verify`.

**Ghi nhớ:** *phase nói Maven phải đi **đến đâu** trong lifecycle; plugin goal nói Maven thực hiện **một tác vụ nào**.* `mvn clean verify` đi qua hai lifecycle và toàn bộ binding liên quan đến `verify`; `mvn compiler:compile` chỉ yêu cầu một goal cụ thể theo điều kiện hiện có. Hiểu ranh giới này giúp chọn đúng lệnh cho local, CI và việc phát hành artifact.

## Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — Running Apache Maven](https://maven.apache.org/run.html)
- [Apache Maven — Plugin Prefix Resolution](https://maven.apache.org/guides/introduction/introduction-to-plugin-prefix-mapping.html)
- [Maven Compiler Plugin — compiler:compile](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html)
- [Maven Surefire Plugin — surefire:test](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Maven Failsafe Plugin — Introduction](https://maven.apache.org/surefire/maven-failsafe-plugin/)
