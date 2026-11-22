# Cú pháp lệnh `mvn`: phase, plugin goal và các tùy chọn

## 1. Đọc đúng một lệnh Maven trước khi chạy

Một lệnh Maven thường trả lời đồng thời ba câu hỏi: **thực hiện việc gì** (phase hoặc plugin goal), **thực hiện trên dự án nào** (POM, project/module được chọn) và **thực hiện với điều kiện nào** (tùy chọn CLI, property, profile, chế độ offline, v.v.).

Cú pháp tổng quát của Maven CLI, trình bày theo hướng dễ đọc:

~~~text
mvn [tùy-chọn] [phase | plugin-prefix:goal | plugin-coordinates:goal] ...
~~~

Dấu `[...]` trong sơ đồ là ký hiệu “có thể có”, **không phải ký tự phải gõ**. Một lời gọi có thể có nhiều phase/goal theo thứ tự, xen các tùy chọn thích hợp. Trong thực tế hãy để các tùy chọn trước mục tiêu để lệnh dễ đọc:

~~~bash
mvn -B --no-transfer-progress clean verify
mvn -DskipTests package
mvn -f subproject/pom.xml test
mvn -pl :app -am verify
mvn dependency:tree
~~~

Ở các lệnh trên:

- `mvn` là chương trình CLI được cài trên máy. Nếu dự án có Maven Wrapper, chạy `./mvnw` trên Linux/macOS hoặc `.\mvnw.cmd` trên PowerShell, rồi truyền **cùng kiểu tham số Maven** theo sau.
- `clean` và `verify` là **phase** của hai lifecycle khác nhau; chúng là mốc quy trình.
- `dependency:tree` là **plugin goal**: yêu cầu goal `tree` của Maven Dependency Plugin.
- `-DskipTests`, `-B`, `-f`, `-pl` và `-am` là **tùy chọn**, thay đổi cách Maven thực hiện công việc; chúng không phải phase/goal.

Bài thực hành này sử dụng cú pháp Maven **3.9.x** cùng JDK **17 trở lên**. Các phiên bản Maven sau có thể thêm/thay đổi tùy chọn, nên khi cần đối chiếu CLI thực tế của máy, dùng `mvn --help` và `mvn --version`.

## 2. Vì sao phải phân biệt phase và plugin goal?

Maven có **build lifecycle** là đường đi tiêu chuẩn cho quá trình build. Mỗi lifecycle chứa nhiều **phase**; Maven gắn **plugin goals** cụ thể với các phase để làm việc thực tế.

~~~text
Một yêu cầu build
       |
       +--> lifecycle: clean
       |          |
       |          +--> phase: clean ------> plugin goal: clean:clean
       |
       +--> lifecycle: default
                  |
                  +--> phase: compile ---> plugin goal: compiler:compile
                  +--> phase: test ------> plugin goal: surefire:test
                  +--> phase: package ---> plugin goal: jar:jar (với packaging=jar)
~~~

Sơ đồ này rút gọn các phase trung gian, ví dụ `process-resources`, `test-compile` và `process-test-resources`. Bản chất cần nhớ:

1. **Lifecycle** định nghĩa thứ tự các phase. Ba lifecycle tích hợp của Maven là `default`, `clean` và `site`.
2. **Phase** là mốc, ví dụ `compile`, `test`, `package`. Lệnh `mvn package` khiến Maven chạy lần lượt các phase thuộc `default` **đến hết** `package`.
3. **Plugin** là đơn vị cung cấp các công việc build. **Goal** là một công việc cụ thể của plugin, ví dụ `maven-compiler-plugin` có goal `compile`.
4. Một phase có thể có **0, 1 hoặc nhiều** goal được gắn (binding). Loại `packaging` và cấu hình POM quyết định nhiều binding.
5. Một goal cũng có thể gọi **trực tiếp** qua CLI. Khi đó không được tự suy luận rằng toàn bộ lifecycle đã chạy đến một phase cụ thể; goal có thể có yêu cầu/fork lifecycle riêng theo mô tả của chính plugin.

Điểm phân biệt quan trọng: `mvn compile` gọi **phase**; `mvn compiler:compile` gọi **goal**. Kết quả của hai lệnh có thể trông giống nhau nếu dự án rất nhỏ, nhưng chúng **không tương đương** về quy trình. `mvn compile` đi qua những phase trước nó, bao gồm xử lý resource; gọi goal biên dịch trực tiếp chỉ yêu cầu goal ấy (trừ các yêu cầu lifecycle do goal khai báo).

### 2.1. Các phase thường dùng

| Lệnh | Ý nghĩa | Bằng chứng dễ thấy |
| --- | --- | --- |
| `mvn validate` | Kiểm tra cấu trúc/cấu hình dự án đến phase `validate` | Maven phân tích POM và thực thi các goal được gắn |
| `mvn compile` | Biên dịch mã nguồn chính | `target/classes` chứa `.class` |
| `mvn test` | Biên dịch/chạy unit test nếu đã cấu hình thích hợp | `target/test-classes`, `target/surefire-reports` |
| `mvn package` | Đến phase đóng gói, thường có chạy test trước | `target/<artifactId>-<version>.jar` với `packaging=jar` |
| `mvn verify` | Chạy đến `verify`, gồm các bước kiểm tra được gắn | Báo cáo build/kiểm tra được cấu hình |
| `mvn install` | Sau `verify`, cài artifact vào local repository | Artifact được lưu trong `~/.m2/repository` |
| `mvn deploy` | Xuất bản artifact lên remote repository đã được cấu hình | Phải có repository và quyền tương ứng |
| `mvn clean` | Chạy đến phase `clean` của lifecycle `clean` | Đầu ra build mặc định trong `target/` được dọn |

`install` không đồng nghĩa với cài ứng dụng vào hệ điều hành; nó cài **Maven artifact vào kho cục bộ** để dự án khác tham chiếu. `deploy` mới liên quan đến kho artifact từ xa và có thể cần cấu hình, chứng thực; không tự chạy `deploy` khi chỉ muốn build học tập.

**Thứ tự phase không rút ngắn được bằng cách chọn tên gần cuối.** Khi gõ:

~~~bash
mvn verify
~~~

Maven vẫn đi qua `validate`, `compile`, `test`, `package` và các phase liên quan trước `verify`. Không cần gõ `mvn compile test package verify`; một lần `mvn verify` là đủ để yêu cầu chạy đến điểm đó.

### 2.2. Tại sao `clean` thường đi cùng `package`?

Lệnh:

~~~bash
mvn clean package
~~~

bao gồm hai mục tiêu độc lập theo thứ tự: chạy `clean` của lifecycle clean, sau đó chạy đến `package` của default lifecycle. Vì `clean` loại kết quả cũ, bạn dễ kết luận file JAR tạo ra sau lệnh này thuộc lần build hiện tại.

Trong dự án `jar` mặc định, `mvn package` **không nhất thiết dọn đầu ra của lần trước**. Nếu vừa sửa file mà chỉ chạy `mvn compile`, một JAR từ lần `package` cũ vẫn có thể tồn tại trong `target/`. Vì vậy khi kiểm chứng pipeline theo từng bước, thường dùng `mvn clean compile`, `mvn clean test` và `mvn clean package`.

### 2.3. Nhiều phase/goal trên cùng một dòng

Maven thực thi các mục tiêu được nêu theo **thứ tự**. Ví dụ trong tài liệu Maven:

~~~bash
mvn clean dependency:copy-dependencies package
~~~

Nghĩa là: dọn build, gọi goal `copy-dependencies` của Dependency Plugin, rồi thực thi default lifecycle đến `package`. Goal ở giữa có thể cần dependency và có hành vi riêng; ví dụ này dùng để **minh họa cách phân tích cú pháp**, không phải lệnh bắt buộc cho mọi dự án.

Nếu một lệnh liệt kê nhiều phase cùng lifecycle, chẳng hạn `mvn test package`, đừng mặc định mỗi phase chỉ chạy một lần. Để build đến `package`, **chỉ dùng `mvn package`**; Maven sẽ tự chạy các phase trước đó.

## 3. Cách viết plugin goal: từ dạng ngắn đến đầy đủ

### 3.1. Dạng thường gặp `prefix:goal`

Một plugin có thể cung cấp nhiều goal. Tên ngắn thường dùng:

~~~bash
mvn help:effective-pom
mvn help:active-profiles
mvn dependency:tree
mvn compiler:compile
~~~

Mỗi lệnh yêu cầu Maven giải quyết **plugin prefix** (ví dụ `help` → Maven Help Plugin) rồi chạy goal tương ứng. Vì có việc phân giải plugin, plugin phiên bản nào được chọn còn phụ thuộc vào POM, plugin management, repository và cơ chế giải quyết phiên bản/prefix.

Ý nghĩa từng ví dụ:

- `help:effective-pom`: xuất POM hiệu lực sau khi áp dụng kế thừa, profile và cấu hình liên quan; hữu ích khi không hiểu giá trị POM đến từ đâu.
- `help:active-profiles`: cho biết profile đang hoạt động trong dự án đang chọn.
- `dependency:tree`: trình bày cây dependency đã giải quyết.
- `compiler:compile`: gọi goal biên dịch của Compiler Plugin trực tiếp; **không** đại diện cho toàn bộ bước kiểm thử/đóng gói.

`mvn test` và `mvn surefire:test` cũng không đồng nghĩa: gọi goal Surefire trực tiếp có thể không tạo mã test/compile đầy đủ từ trạng thái sạch. Hãy dùng `mvn test` nếu mục tiêu là chạy **quy trình kiểm thử tiêu chuẩn**.

### 3.2. Dạng tọa độ đầy đủ của plugin

Khi muốn chỉ rõ một plugin cụ thể, Maven hỗ trợ dạng:

~~~text
mvn groupId:artifactId:version:goal
~~~

Ví dụ, dùng phiên bản Help Plugin cụ thể:

~~~bash
mvn org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom
~~~

Dạng này xác định rõ `groupId`, `artifactId`, `version` và `goal`, giúp giảm mơ hồ khi tra cứu hay kiểm tra plugin. Phiên bản ghi trong lệnh là phiên bản **plugin**, không phải phiên bản artifact ứng dụng. Thường trong dự án dài hạn nên quản lý phiên bản plugin qua `pom.xml` hoặc POM cha, và dùng dạng ngắn khi đã cấu hình rõ.

### 3.3. Xem tài liệu của một goal ngay từ CLI

Ví dụ:

~~~bash
mvn help:describe -Dplugin=org.apache.maven.plugins:maven-compiler-plugin -Dgoal=compile -Ddetail
~~~

Lệnh này dùng goal `describe` của Help Plugin để tra thông tin một goal khác. Các tham số `-Dplugin`, `-Dgoal` và `-Ddetail` là **user properties truyền vào plugin Help**; chúng không biến từ khóa `compile` thành một phase được chạy.

Không phải plugin nào cũng có goal giống nhau; không suy đoán `plugin:goal` từ tên tiện miệng. Khi không chắc, tra tài liệu plugin hoặc `help:describe`.

## 4. Tùy chọn `-D`: truyền một property vào Maven

Cú pháp phổ biến:

~~~text
-Dten=gia-tri
-Dten
~~~

Dạng thứ hai không ghi giá trị tường minh, thường được hiểu là giá trị `true` đối với các tham số boolean hỗ trợ. Trong Maven CLI, `-D` khai báo **user property**; cách property ảnh hưởng đến build phụ thuộc plugin và POM có đọc property ấy hay không.

Ví dụ thiết thực nhất với dự án có unit test:

~~~bash
mvn -DskipTests package
mvn -DskipTests=true package
mvn -Dmaven.test.skip=true package
~~~

Các lệnh cần **phân biệt**:

| Tùy chọn | Ý nghĩa thông dụng |
| --- | --- |
| `-DskipTests` | Surefire/Failsafe bỏ **thực thi** test; test source thường vẫn được biên dịch |
| `-Dmaven.test.skip=true` | Compiler/Surefire/Failsafe hỗ trợ bỏ cả **biên dịch và thực thi** test |
| Không truyền hai property trên | Test sẽ chạy bình thường nếu dự án có test và plugin được cấu hình/phát hiện đúng |

Không dùng `-DskipTests` để che lỗi khi xác minh chất lượng hoặc làm bài thực hành về test. `BUILD SUCCESS` sau lệnh bỏ test **không chứng minh** test đã pass.

Một property khác có thể chọn test cụ thể qua Surefire:

~~~bash
mvn -Dtest=GreetingTest test
~~~

Ví dụ này chỉ chạy lớp `GreetingTest` thuộc quy ước và khả năng nhận diện của Surefire, nếu lớp đó tồn tại. Nếu tên test sai, lệnh có thể thất bại vì không tìm thấy test được yêu cầu.

**Phân biệt property Maven với system property của ứng dụng:** `mvn -Ddemo.name=Lan package` chỉ đặt property cho quá trình Maven. Sau đó chạy `java -cp ... App` là một **tiến trình JVM khác**; property không tự truyền sang JVM mới. Muốn cấp cho chương trình Java khi chạy trực tiếp, gõ `java -Ddemo.name=Lan -cp ... App`. Bài thực hành ở mục 9 sẽ chứng minh bằng mã chạy được.

**Chú ý môi trường shell:** nếu giá trị có khoảng trắng hoặc ký tự đặc biệt, cách đặt dấu nháy có thể khác giữa PowerShell, Bash và CMD. Kiểm tra cú pháp quoting của shell và tránh đưa mật khẩu/token lên command line, nơi chúng có thể lộ trong history, log hoặc danh sách tiến trình.

## 5. Các nhóm tùy chọn CLI thường dùng

Các tùy chọn trong bảng sau áp dụng cho Maven 3.9.x. Bạn không phải nhớ toàn bộ; hãy hiểu mục tiêu và giới hạn.

### 5.1. Kiểm tra lệnh và điều khiển log

| Tùy chọn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `-h`, `--help` | `mvn --help` | Xem hướng dẫn các tùy chọn Maven CLI |
| `-v`, `--version` | `mvn -v` | Xem phiên bản Maven, JVM và môi trường; không cần chạy build |
| `-V`, `--show-version` | `mvn -V test` | In thông tin phiên bản **và tiếp tục** build |
| `-q`, `--quiet` | `mvn -q test` | Giảm log, chủ yếu hiển thị lỗi |
| `-X`, `--debug` | `mvn -X test` | Chi tiết debug để truy nguyên lỗi |
| `-e`, `--errors` | `mvn -e test` | In chi tiết stack trace lỗi |
| `-B`, `--batch-mode` | `mvn -B verify` | Chạy ở chế độ không tương tác, phù hợp CI |
| `-ntp`, `--no-transfer-progress` | `mvn -ntp test` | Không in tiến độ tải lên/tải xuống |
| `-l`, `--log-file` | `mvn -l build.log test` | Ghi output của build vào file log |

Thông tin `-X` hoặc log CI có thể chứa URL repository nội bộ, đường dẫn, properties hoặc nội dung nhạy cảm tùy dự án. **Rà soát log trước khi chia sẻ**, và giữ `build.log` ngoài mã nguồn được commit khi không cần lưu.

Khi cần một lệnh dễ đọc trong pipeline CI:

~~~bash
mvn -B -ntp clean verify
~~~

`-B` và `-ntp` chỉ thay đổi cách chạy/ghi log theo mục đích trình bày; chúng không làm test tự động pass và không tạo thêm phase.

### 5.2. Chọn cấu hình, repository và profile

| Tùy chọn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `-f`, `--file` | `mvn -f examples/app/pom.xml test` | Chọn POM khác, hoặc thư mục chứa `pom.xml` |
| `-P`, `--activate-profiles` | `mvn -Pdev verify` | Bật profile đã được khai báo phù hợp; nhiều profile có thể phân tách bằng dấu phẩy |
| `-s`, `--settings` | `mvn -s /path/to/settings.xml test` | Dùng user settings ở đường dẫn chỉ định |
| `-gs`, `--global-settings` | `mvn -gs /path/to/global-settings.xml validate` | Thay global settings file khi cần |
| `-o`, `--offline` | `mvn -o test` | Không truy cập repository từ xa trong lần chạy đó |
| `-U`, `--update-snapshots` | `mvn -U package` | Kiểm tra lại các SNAPSHOT cập nhật và một số tình huống release còn thiếu theo Maven |
| `-nsu`, `--no-snapshot-updates` | `mvn -nsu test` | Hạn chế kiểm tra cập nhật SNAPSHOT |

`-f` hữu ích trong mono-repo có nhiều project Maven: nó chọn **POM điều khiển lệnh**, không chuyển nội dung file hay tự sửa dependency. Nếu chọn POM cha trong dự án nhiều module, Maven có thể kích hoạt cả reactor do POM cha khai báo.

`-Pdev` **không tự tạo** profile tên `dev`. Profile phải đã được khai báo/khả dụng qua POM hoặc settings thích hợp. `-P` là cơ chế chọn cấu hình; việc bật profile có thể thay đổi dependency, plugin, properties hoặc những thành phần POM mà profile cho phép.

`-o` hữu ích cho build khi cache đã có đủ plugin/dependency, nhưng sẽ thất bại nếu artifact cần thiết chưa có ở local repository. `-U` **không tương đương** xóa cache và không nhất thiết buộc tải lại mọi release đã có. Sử dụng nó khi thực sự cần cập nhật các artifact theo chính sách repository.

### 5.3. Chọn module của reactor

Dùng khi POM gốc có `<modules>` và Maven nhận diện một **multi-module reactor**.

| Tùy chọn | Ví dụ | Điều khiển |
| --- | --- | --- |
| `-pl`, `--projects` | `mvn -pl :app test` | Chỉ chọn những project liệt kê trong reactor |
| `-am`, `--also-make` | `mvn -pl :app -am verify` | Build thêm các project trong reactor mà project được chọn cần |
| `-amd`, `--also-make-dependents` | `mvn -pl :core -amd test` | Build thêm các project trong reactor phụ thuộc vào project được chọn |
| `-rf`, `--resume-from` | `mvn -rf :app package` | Tiếp tục reactor từ project chỉ định |
| `-N`, `--non-recursive` | `mvn -N validate` | Chỉ xử lý project hiện tại, không đi vào project con |
| `-T`, `--threads` | `mvn -T 1C verify` | Điều chỉnh số thread cho build nhiều project, ở đây khoảng một thread trên một lõi CPU |
| `-fae`, `--fail-at-end` | `mvn -fae verify` | Cố chạy tiếp các project không bị ảnh hưởng và báo fail ở cuối |
| `-ff`, `--fail-fast` | `mvn -ff verify` | Dừng reactor sớm khi một project thất bại |
| `-fn`, `--fail-never` | `mvn -fn verify` | Không trả trạng thái thất bại dù build có project fail; **tránh dùng trong CI kiểm định** |

`:app` là cách chọn artifactId khi nó xác định được project trong reactor; dạng khác là đường dẫn tương đối như `app` hoặc `groupId:artifactId`. `-pl` chọn module, còn `-am`/`-amd` quyết định thêm module nào liên quan theo đồ thị phụ thuộc. **`-am` không tự thêm một dependency còn thiếu vào POM.**

`-rf` hữu ích sau khi build lỗi rồi đã sửa nguyên nhân; nhưng khi bắt đầu từ checkout sạch, việc chỉ resume từ `app` có thể thiếu artifact `core` chưa có trong local repository. Hãy chủ động đảm bảo các tiền đề đã được build hoặc dùng lệnh reactor có `-am` phù hợp.

`-T` chỉ thực sự giúp được khi cấu trúc reactor có phần việc có thể chạy song song và các plugin sử dụng phù hợp. Nếu gặp lỗi khó tái hiện khi build song song, thử build tuần tự để so sánh; không bật song song chỉ vì số thread càng lớn càng tốt.

## 6. Kết hợp các thành phần trong một lệnh

Tách một lệnh điển hình:

~~~bash
mvn -B -ntp -Pci -DskipTests=false -pl :app -am clean verify
~~~

Đọc theo từng nhóm:

| Thành phần | Vai trò |
| --- | --- |
| `mvn` | Gọi Maven CLI |
| `-B -ntp` | Chế độ batch và log không có transfer progress |
| `-Pci` | Kích hoạt profile tên `ci` **nếu dự án có định nghĩa** |
| `-DskipTests=false` | Đặt property do plugin hỗ trợ đọc; không chủ động bỏ test |
| `-pl :app` | Chọn project `app` của reactor |
| `-am` | Thêm các project trong reactor mà `app` phụ thuộc |
| `clean verify` | Làm sạch rồi thực thi default lifecycle đến `verify` |

Đừng copy lệnh này vào dự án không có profile `ci` hoặc không có module `app`. Thay vì ghi nhớ cả chuỗi, hãy ghép dần: chọn **kết quả cần đạt** trước (`verify`), rồi thêm tùy chọn thực sự phục vụ mục đích.

Một số ví dụ cho các công việc hằng ngày:

~~~bash
mvn -v
mvn clean compile
mvn test
mvn -Dtest=GreetingTest test
mvn clean package
mvn -B -ntp clean verify
mvn dependency:tree
mvn help:effective-pom
~~~

Các lệnh trên đều có ý nghĩa độc lập; không bắt buộc chạy theo thứ tự liệt kê. Đối với code cần đảm bảo chất lượng, thông thường chọn `verify` làm mốc build toàn diện hơn `compile`.

## 7. Hai khác biệt dễ gây hiểu nhầm khi đọc lệnh

### 7.1. `-D` không giống tham số của JVM chạy chương trình

Một command line có thể chạy **Maven** hoặc chạy **chương trình Java**:

~~~bash
mvn -Ddemo.name=Lan package
java -Ddemo.name=Lan -cp target/cli-demo-1.0.0.jar vn.example.mavencli.App
~~~

Dù có cùng cú pháp `-D`, đối tượng nhận property ở lệnh đầu là **Maven**, còn ở lệnh thứ hai là **JVM chạy `App`**. Chúng là hai tiến trình riêng.

Nếu bạn đặt `-Ddemo.name=Lan` vào lệnh Maven, không nên kỳ vọng chương trình Java chạy sau đó tự động đọc được giá trị `Lan` từ một JVM mới. Một số plugin có thể cấu hình để truyền property sang test JVM, nhưng đó là **hành vi plugin/configuration**, không phải quy tắc chung cho mọi chương trình.

### 7.2. Gọi goal không đồng nghĩa đã chạy cả lifecycle

So sánh:

~~~bash
mvn compile
mvn compiler:compile
~~~

Lệnh đầu chạy default lifecycle đến `compile`, gồm các phase và goal được gắn trước đó. Lệnh thứ hai gọi trực tiếp `compiler:compile`; đây là một công việc cụ thể của Compiler Plugin. Nếu dự án có code generation hoặc resource processing bắt buộc chạy ở phase trước, hai cách gọi có thể đem lại kết quả khác nhau.

Tương tự, `mvn dependency:tree` là câu lệnh kiểm tra dependency graph, không phải yêu cầu Maven phải chạy unit test rồi đóng gói sản phẩm. Mục đích nào thì chọn đúng mục tiêu đó.

## 8. Thực hành A: dự án Java 17 có code, test và POM đầy đủ

Dựng một dự án nhỏ tên `cli-demo`. Ví dụ độc lập này cho phép quan sát `mvn` với phase, goal, `-D`, profile và file artifact.

Cây thư mục:

~~~text
cli-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/mavencli/
    │   ├── App.java
    │   └── Greeting.java
    └── test/java/vn/example/mavencli/
        └── GreetingTest.java
~~~

### 8.1. POM dự án: `cli-demo/pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>cli-demo</artifactId>
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
        </plugins>
    </build>

    <profiles>
        <profile>
            <id>dev</id>
            <properties>
                <demo.profile>development</demo.profile>
            </properties>
        </profile>
    </profiles>
</project>
~~~

`<packaging>jar</packaging>` gắn các goal mặc định với nhiều phase, chẳng hạn Compiler Plugin ở compile và JAR Plugin ở package. `<profiles>` định nghĩa profile tên `dev` dùng để thử CLI; nó không tự bật nếu không có điều kiện kích hoạt hay tùy chọn `-Pdev`. Phiên bản plugin/test được khai báo rõ để giảm khác biệt giữa các máy.

### 8.2. Mã ứng dụng

File `src/main/java/vn/example/mavencli/Greeting.java`:

~~~java
package vn.example.mavencli;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + name + "!";
    }
}
~~~

File `src/main/java/vn/example/mavencli/App.java`:

~~~java
package vn.example.mavencli;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        String name = System.getProperty("demo.name", "Maven");
        System.out.println(Greeting.message(name));
    }
}
~~~

`App` đọc property từ **JVM mà ứng dụng đang chạy**; khi property vắng mặt, nó dùng tên `Maven`.

File `src/test/java/vn/example/mavencli/GreetingTest.java`:

~~~java
package vn.example.mavencli;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingTest {
    @Test
    void saysHello() {
        assertEquals("Hello, Maven!", Greeting.message("Maven"));
    }

    @Test
    void rejectsBlankName() {
        assertThrows(IllegalArgumentException.class,
                () -> Greeting.message(" "));
    }
}
~~~

Đây là chương trình Java 17+ đầy đủ với hai unit test JUnit 5, không cần thư viện runtime nào ngoài JDK cho ứng dụng. Chú ý mã test không được đóng gói vào JAR chính theo cấu hình tiêu chuẩn.

### 8.3. Thử các phase

Từ thư mục `cli-demo`, chạy lần lượt và kiểm tra đầu ra:

~~~bash
mvn -v
mvn clean compile
mvn clean test
mvn clean package
~~~

Sau từng lệnh có `clean`:

| Lệnh | File/đầu ra tiêu biểu |
| --- | --- |
| `mvn clean compile` | `target/classes/vn/example/mavencli/App.class` và `Greeting.class` |
| `mvn clean test` | Ngoài class chính, có `target/test-classes/.../GreetingTest.class` và `target/surefire-reports/`; 2 test pass |
| `mvn clean package` | Đầu ra trên cộng `target/cli-demo-1.0.0.jar` |

Lệnh chạy chương trình từ JAR:

~~~bash
java -cp target/cli-demo-1.0.0.jar vn.example.mavencli.App
~~~

Đầu ra **chính xác**:

~~~text
Hello, Maven!
~~~

JAR ở đây chưa khai báo `Main-Class` trong manifest, nên không mặc nhiên chạy bằng `java -jar`. Khi dùng `java -cp`, bạn ghi rõ tên lớp có `main`.

### 8.4. Thử một plugin goal

Chạy:

~~~bash
mvn help:effective-pom
mvn dependency:tree
~~~

Goal đầu hiển thị effective POM, giúp bạn kiểm tra cấu hình plugin, profile và dependency. Goal sau hiển thị cây dependency, trong đó bạn sẽ thấy JUnit là dependency có scope `test` cùng các dependency bắc cầu tương ứng.

Các goal này hữu ích cho chẩn đoán và khám phá dự án. Chúng **không** tự thay thế lệnh `mvn clean verify` để chứng minh bài test và đóng gói hoạt động.

### 8.5. Thử property `-D`

Chọn một test bằng CLI:

~~~bash
mvn -Dtest=GreetingTest test
~~~

Do class `GreetingTest` có hai phương thức gắn `@Test`, khi không có cấu hình lọc khác, báo cáo thường cho thấy hai test được chạy.

Thử bỏ chạy test:

~~~bash
mvn -DskipTests package
~~~

Đọc log để xác nhận Surefire bỏ thực thi test (đừng gọi đây là “test PASS”). Sau đó khôi phục cách build kiểm tra chuẩn:

~~~bash
mvn clean verify
~~~

Kiểm chứng khác biệt property giữa Maven và Java:

~~~bash
mvn -Ddemo.name=Lan package
java -cp target/cli-demo-1.0.0.jar vn.example.mavencli.App
java -Ddemo.name=Lan -cp target/cli-demo-1.0.0.jar vn.example.mavencli.App
~~~

Vì POM và mã ví dụ không cấu hình goal nào để truyền `demo.name` từ Maven sang chương trình Java chạy riêng, hai lần gọi Java có kết quả tương ứng:

~~~text
Hello, Maven!
Hello, Lan!
~~~

Đây là đầu ra của **hai lần chạy Java theo thứ tự**, không phải toàn bộ log Maven.

### 8.6. Thử profile `-P`

POM mẫu có profile `dev`, nên bạn có thể chạy:

~~~bash
mvn -Pdev help:active-profiles
mvn -Pdev help:effective-pom
~~~

Quan sát profile `dev` được kích hoạt và property `demo.profile` được khai báo với giá trị `development` trong effective POM. Nếu chạy `mvn help:active-profiles` **không có `-Pdev`**, profile này không được bật bởi chính cấu hình mẫu (trừ khi môi trường có cơ chế kích hoạt khác).

Dùng `-P` để chọn cấu hình **đã tồn tại**; đừng tưởng rằng gõ `-Pproduction` sẽ tự tạo cấu hình production trong một dự án chưa khai báo profile ấy.

### 8.7. Thử chọn POM với `-f`

Từ **thư mục cha của `cli-demo`**:

~~~bash
mvn -f cli-demo/pom.xml clean verify
~~~

Lệnh chọn đúng POM có đường dẫn `cli-demo/pom.xml`, kể cả khi bạn không `cd` vào thư mục con. Nếu chạy trong `cli-demo`, lệnh tương đương về POM đang được điều khiển là:

~~~bash
mvn -f pom.xml clean verify
~~~

Dùng đường dẫn hợp lệ theo vị trí terminal hiện tại. `-f` không tự tìm một POM tùy ý ngoài đường dẫn bạn chỉ định.

## 9. Thực hành B: đọc các tùy chọn reactor trong dự án nhiều module

Giả sử có dự án Maven multi-module, với POM gốc định nghĩa `core` và `app`; trong `app/pom.xml` có dependency thực sự đến artifact `core`:

~~~text
shop/
├── pom.xml             # aggregator <modules>core, app</modules>
├── core/pom.xml        # artifactId: core
└── app/pom.xml         # artifactId: app, dependency -> core
~~~

Đây là **sơ đồ quan hệ**, không phải trọn bộ source/POM để copy và build ngay. Chỉ việc đặt hai thư mục vào `<modules>` không tự tạo dependency từ `app` sang `core`.

Từ root `shop`:

~~~bash
mvn clean verify
mvn -pl :core test
mvn -pl :app -am package
mvn -pl :core -amd test
mvn -N validate
~~~

Cách đọc:

- `mvn clean verify`: build toàn reactor theo POM gốc; Maven xác định thứ tự project từ các quan hệ dependency thực tế.
- `-pl :core`: chỉ chọn `core` để kiểm thử; các module khác không được tự chọn.
- `-pl :app -am`: chọn `app` và những project cần thiết trong reactor, ví dụ `core`. Đây là lựa chọn thường dùng từ checkout sạch.
- `-pl :core -amd`: chọn `core` và những project phụ thuộc vào `core` trong reactor, ví dụ `app`, để quan sát tác động từ thay đổi thư viện.
- `-N`: khi chạy ở POM gốc, không đệ quy vào các module; thích hợp cho thao tác chỉ cần thực hiện ở parent.

Khi một reactor build thất bại ở `app`, lệnh:

~~~bash
mvn -rf :app verify
~~~

có thể resume từ `app`. Tuy nhiên nếu artifact `core` chưa có sẵn hoặc đã thay đổi mà chưa được build, việc resume như vậy có thể thất bại do thiếu dependency. Hãy đánh giá trạng thái module cần thiết, rồi cân nhắc `mvn -pl :app -am verify` hoặc build đầy đủ.

Với hệ thống lớn, `-T 1C` có thể tăng tốc ở những phần độc lập, nhưng không thay đổi các ràng buộc dependency và có thể làm lộ plugin không an toàn khi chạy song song. Khi điều tra lỗi song song, thử bỏ `-T` trước.

## 10. Phân tích log và tìm nguyên nhân khi một lệnh Maven lỗi

Đừng chỉ nhìn `BUILD FAILURE`. Cách đọc có thể lặp lại:

1. **Xác định lệnh và mục tiêu:** Bạn gọi phase hay plugin goal? Có `-pl`, `-P`, `-D`, `-o` hoặc `-f` không?
2. **Xác định project/module:** Với reactor, xem mục `Reactor Summary` và module cuối cùng có lỗi.
3. **Xác định plugin goal/phase đầu tiên thất bại:** Có thể là `compiler:compile` do Java source, `surefire:test` do unit test, hoặc `dependency:tree` do không giải quyết được dependency.
4. **Đọc thông báo gốc trước stack trace dài:** Ví dụ “invalid target release”, “Could not resolve artifact”, hay tên test và giá trị kỳ vọng khác thực tế.
5. **Dùng `-e` hoặc `-X` khi log thường chưa đủ:** Ghi nhận đúng phần thông tin cần thiết, không chia sẻ toàn bộ log debug nếu có cấu hình riêng tư.

Một số tình huống thường gặp:

| Triệu chứng | Đọc lại cú pháp và kiểm tra gì? |
| --- | --- |
| `Unknown lifecycle phase` | Tên phase sai hoặc gõ tùy chọn/giá trị vào vị trí mục tiêu; xem `mvn --help` |
| `No plugin found for prefix ...` | Plugin prefix sai, plugin chưa được khai báo/không giải quyết được, hoặc repository có vấn đề; thử tọa độ plugin đầy đủ |
| `The requested profile ... could not be activated` | `-P...` trỏ tới profile không tồn tại/không khả dụng; xem `help:active-profiles` và POM/settings |
| `Could not find the selected project in the reactor` | `-pl` đang chọn sai `artifactId`, `groupId:artifactId` hoặc đường dẫn; chạy từ đúng POM gốc |
| `Could not resolve dependencies` ở `-pl :app` | Có thể thiếu upstream `core` chưa build/install; dùng `-am` đúng quan hệ dependency |
| `release version 17 not supported` | Maven chạy bằng JDK không hỗ trợ release 17; xem `mvn -v` và `JAVA_HOME` |
| Plugin/Dependency không tải được khi có `-o` | Cache chưa chứa đủ artifact; bỏ offline khi môi trường cho phép tải qua repository tin cậy |
| Test sai nhưng build vẫn `SUCCESS` | Tìm `-DskipTests`, `-Dmaven.test.skip`, cấu hình Surefire và số test đã thực chạy |
| `-q` làm log quá ít | Bỏ `-q` hoặc dùng `-e` để thấy lỗi có ngữ cảnh |
| Build thất bại mà CI báo thành công | Kiểm tra có `-fn` hoặc script nuốt exit code hay không; không dùng `-fn` để kiểm định |
| `mvn -f ...` dùng sai module | Xác định đường dẫn POM tương đối với thư mục terminal, rồi xem `effective-pom` |
| `-T` khiến kết quả không ổn định | So sánh build tuần tự, kiểm tra plugin tương thích và tài nguyên dùng chung |

**Cẩn thận khi chạy lệnh tự động:** Không dùng `-fn` cho CI cần chặn lỗi. Trong shell script, kiểm tra mã thoát của tiến trình Maven; câu “Build failure” trong log và **exit code** là hai tín hiệu khác nhau nếu có tùy chọn can thiệp. Không tự kích hoạt `deploy` hay plugin có tác dụng phát hành/xóa dữ liệu khi mục tiêu chỉ là học lệnh build.

## 11. Bài tập vận dụng: dự đoán trước rồi quan sát

**Bài tập 1 — Phân loại đối số.** Với `mvn -B -DskipTests=false clean package`, hãy chỉ ra đâu là executable, tùy chọn, property và phase. Sau đó giải thích vì sao `package` vẫn đi qua `compile` và `test` trong default lifecycle.

**Bài tập 2 — Phân biệt phase và goal.** Chạy trên `cli-demo`: `mvn clean compile` rồi xem `target/classes`; tiếp theo chạy `mvn help:effective-pom`. Viết hai câu mô tả vì sao lệnh đầu đi qua lifecycle còn lệnh sau là một goal chuyên biệt.

**Bài tập 3 — Test và property.** Chạy `mvn -Dtest=GreetingTest test`, xác nhận hai test PASS; sau đó `mvn -DskipTests package`, quan sát log chỉ rõ test đã bị bỏ; cuối cùng `mvn clean verify` để khôi phục bằng chứng kiểm định đầy đủ.

**Bài tập 4 — Profile có thật.** Dùng `-Pdev` trên dự án mẫu để xem profile được kích hoạt và property `demo.profile` trong effective POM. Bỏ `-Pdev` và so sánh. Đừng tự đặt tên profile khác nếu chưa khai báo.

**Bài tập 5 — Shell và JVM.** Build JAR, chạy Java với và không có `-Ddemo.name=Lan`. Giải thích vì sao property ở lệnh Java mới ảnh hưởng trực tiếp đến `System.getProperty` trong một JVM độc lập.

**Bài tập 6 — Lệnh trên reactor.** Với dự án minh họa `shop` có dependency `app → core`, diễn giải bằng lời sự khác biệt giữa `-pl :app`, `-pl :app -am`, `-pl :core -amd` và `-rf :app`. Chỉ rõ lệnh nào phù hợp khi checkout chưa có artifact của `core`.

**Bài tập 7 — Tự sửa một câu lệnh lỗi.** Với lệnh `mvn -Pdev -pl :missing -o package` bị lỗi, hãy lần lượt kiểm tra profile, module và cache offline. Chỉ thay một điều kiện một lần để nhận diện nguyên nhân, thay vì thêm nhiều tùy chọn đoán mò.

## 12. Checklist nắm vững cú pháp Maven CLI

Bạn có thể xem là đã học xong khi tự làm được các việc sau:

- Nhìn `mvn clean verify` và giải thích được **hai lifecycle**, **thứ tự thực thi** và các phase chạy tới `verify`.
- Nhìn `mvn compiler:compile` và giải thích vì sao gọi goal trực tiếp **khác** yêu cầu phase `compile`.
- Nhìn `mvn help:effective-pom` hoặc `mvn dependency:tree` và biết đó là **plugin goal**, không phải phase.
- Truyền một property qua `-D`, kích hoạt một profile có thật qua `-P` và chọn POM qua `-f`.
- Dùng `-pl` cùng `-am`/`-amd` có chủ đích trong reactor, và biết hạn chế của `-rf`.
- Biết khi nào dùng `-B`, `-ntp`, `-e`, `-X`, `-o`, `-U` mà không che lỗi test hoặc nhầm log ít với build thành công.
- Đọc đúng số test chạy, file JAR tạo ra, module thất bại và mã thoát của Maven.

Mục tiêu cuối cùng là **tự chọn được lệnh ngắn nhất phản ánh đúng công việc và giải thích được các cờ trong đó**. Các tùy chọn Maven chỉ có giá trị khi bạn hiểu chúng thay đổi đầu vào, cách thực thi hay phạm vi build nào.

## 13. Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): lifecycle, phase, binding và ví dụ trộn phase/goal.
- [Apache Maven — Maven CLI Options Reference](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html): danh sách các cờ CLI của Maven 3.9.
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html): reactor, `-pl`, `-am`, `-amd`, `-rf` và thứ tự module.
- [Apache Maven — Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html): cách khai báo/kích hoạt profile.
- [Apache Maven — Guide to Configuring Maven](https://maven.apache.org/configure): `.mvn/maven.config`, `.mvn/jvm.config` và cấu hình liên quan.
