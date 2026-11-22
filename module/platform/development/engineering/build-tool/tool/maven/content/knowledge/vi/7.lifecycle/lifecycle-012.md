# Binding mặc định theo packaging và điều kiện một phase có công việc trong Maven

## 1. Vì sao cùng lệnh Maven mà các dự án làm việc khác nhau?

Xét hai dự án đều chạy:

~~~bash
mvn package
~~~

Dự án có **packaging=jar** thường biên dịch Java, xử lý resource, chạy kiểm thử phù hợp rồi tạo file JAR. Một dự án chỉ chứa POM cha với **packaging=pom** có thể hoàn tất chính lệnh này mà **không biên dịch Java và không tạo JAR**. Điều đó không mâu thuẫn: hai dự án dùng cùng **lifecycle và phase**, nhưng Maven chọn **plugin goal được gắn (bound)** theo kiểu packaging và cấu hình hiệu lực của từng dự án.

**Binding** là sự liên kết giữa một **plugin goal** (công việc cụ thể) và một **lifecycle phase** (mốc trong quy trình build).

Ba khái niệm cần phân biệt:

| Khái niệm | Nghĩa | Ví dụ |
| --- | --- | --- |
| **Lifecycle** | Một chuỗi các phase Maven chạy theo thứ tự. | **default**, **clean**, **site**. |
| **Phase** | Một mốc trong lifecycle, chưa tự định nghĩa thao tác thực thi. | **validate**, **compile**, **test**, **package**, **verify**. |
| **Plugin goal** | Một tác vụ cụ thể do plugin cung cấp. | **compiler:compile**, **surefire:test**, **jar:jar**. |
| **Binding** | Quy định goal nào chạy khi Maven đi qua phase nào. | **compiler:compile** được gắn vào **compile** đối với packaging **jar**. |
| **Packaging** | Loại dự án/artifact; ảnh hưởng tập binding mặc định của default lifecycle. | **jar**, **war**, **pom**, **ear**, **maven-plugin**. |

**Kết luận quan trọng:** Một phase nằm trong lifecycle **không có nghĩa phase đó mặc nhiên chạy một thao tác**. Phase chỉ thực hiện công việc của plugin khi **có ít nhất một goal được bind** tại phase ấy; goal có thể đến từ packaging, cấu hình trong POM hoặc cơ chế extension phù hợp.

## 2. Maven có những lifecycle nào?

Maven cung cấp ba lifecycle dựng sẵn:

- **default**: quy trình xây dựng, kiểm thử, đóng gói và phát hành artifact.
- **clean**: quy trình dọn kết quả build, nổi bật là goal **clean:clean** tại phase **clean**.
- **site**: quy trình tạo và xuất bản trang báo cáo/tài liệu, thường qua **site:site** và **site:deploy**.

Một số phase chính của **default lifecycle** theo thứ tự:

~~~text
validate
   |
initialize
   |
generate-sources
   |
process-sources
   |
generate-resources
   |
process-resources
   |
compile
   |
process-classes
   |
generate-test-sources / process-test-sources
   |
generate-test-resources / process-test-resources
   |
test-compile
   |
process-test-classes
   |
test
   |
prepare-package
   |
package
   |
pre-integration-test
   |
integration-test
   |
post-integration-test
   |
verify
   |
install
   |
deploy
~~~

Sơ đồ giữ thứ tự những mốc quan trọng; để tra cứu toàn bộ phase và thứ tự chính xác, xem tài liệu Lifecycle Reference của đúng phiên bản Maven.

Khi gọi:

~~~bash
mvn verify
~~~

Maven xét các phase của **default lifecycle** từ đầu **đến và bao gồm verify** theo thứ tự, và thực thi các goal đã được gắn vào mỗi phase. Nó **không tự chạy install hoặc deploy**, vì hai phase này nằm sau verify.

Khi gọi:

~~~bash
mvn clean verify
~~~

Maven chạy các phase tới **clean** trong lifecycle **clean**, sau đó các phase tới **verify** trong lifecycle **default**. Hai từ **clean** và **verify** thuộc **hai lifecycle khác nhau**; việc chạy clean không mặc định xảy ra chỉ vì gọi verify.

**Không nhầm tên phase với goal:** **compile** là phase; **compiler:compile** là goal. **package** là phase; **jar:jar** hoặc **war:war** là goal đóng gói tùy loại dự án.

## 3. Binding mặc định được xác định từ packaging

Trong POM, phần tử **packaging** chọn kiểu đóng gói; nếu vắng mặt, Maven mặc định chọn **jar**:

~~~xml
<packaging>jar</packaging>
~~~

Maven đã định nghĩa những binding mặc định cho các kiểu packaging phổ biến. Bảng sau mô tả các goal điển hình của **default lifecycle** theo tài liệu Maven:

| Phase | packaging **jar** | packaging **war** | packaging **pom** |
| --- | --- | --- | --- |
| **process-resources** | **resources:resources** | **resources:resources** | Không có goal mặc định |
| **compile** | **compiler:compile** | **compiler:compile** | Không có goal mặc định |
| **process-test-resources** | **resources:testResources** | **resources:testResources** | Không có goal mặc định |
| **test-compile** | **compiler:testCompile** | **compiler:testCompile** | Không có goal mặc định |
| **test** | **surefire:test** | **surefire:test** | Không có goal mặc định |
| **package** | **jar:jar** | **war:war** | Không có goal mặc định |
| **install** | **install:install** | **install:install** | **install:install** |
| **deploy** | **deploy:deploy** | **deploy:deploy** | **deploy:deploy** |

Bảng hiển thị binding mặc định do packaging cung cấp. **Các plugin execution được cấu hình thêm có thể làm xuất hiện công việc tại bất kỳ phase hợp lệ nào**, kể cả những ô trong bảng ghi “không có goal mặc định”.

Các điểm cần hiểu rõ:

- **jar** mặc định biên dịch nguồn Java chính, biên dịch test, gọi Surefire và đóng gói JAR khi đi tới các phase tương ứng. Những phase không có binding riêng như **initialize**, **generate-sources**, **prepare-package** hoặc **verify** vẫn có thể trống.
- **war** gần giống jar ở các phase xử lý Java/test nhưng tại **package** gọi **war:war** để đóng gói ứng dụng web, thay vì **jar:jar**.
- **pom** thường dùng cho parent, BOM hoặc aggregator. Mặc định không biên dịch nguồn Java và không tạo JAR/WAR khi gọi **package**. Tuy vậy vẫn có goal mặc định **install** và **deploy** để cài/phát hành POM nếu thực thi đến các phase đó và cấu hình phù hợp.
- Khi không có **packaging** trong POM, mặc định là **jar**, **không phải pom**. Một parent hoặc aggregator nên khai báo rõ **<packaging>pom</packaging>**.
- Binding mặc định có thể khác đối với **ear**, **ejb**, **rar**, **maven-plugin** hoặc packaging tùy biến từ extension. Không suy diễn từ jar sang tất cả kiểu dự án.

**Version plugin cụ thể không được xác định chỉ từ tên phase.** Nó phụ thuộc vào Maven, Super POM, pluginManagement, parent POM và cấu hình hiệu lực. Nếu cần build tái lập, hãy kiểm soát phiên bản plugin một cách có chủ đích.

## 4. Những packaging khác: ear và maven-plugin

Không phải packaging nào cũng chỉ thay goal ở **package**.

**Packaging ear** dành cho Java Enterprise Application Archive. Theo bảng binding điển hình trong tài liệu Maven:

- **generate-resources**: **ear:generate-application-xml**;
- **process-resources**: **resources:resources**;
- **package**: **ear:ear**;
- **install/deploy**: các goal tương ứng của Install/Deploy Plugin.

Như vậy không nên mặc nhiên nói EAR sẽ chạy đầy đủ **compiler:compile** và **surefire:test** của packaging jar. Những việc đó cần xem binding thực tế và cấu hình dự án.

**Packaging maven-plugin** dành cho một plugin Maven. Nó có thể có binding **plugin:descriptor** ở **generate-resources**, các goal biên dịch/test quen thuộc và thêm **plugin:addPluginArtifactMetadata** ở **package** cùng với **jar:jar**. Mục đích là tạo JAR chứa plugin descriptor/metadata phù hợp để Maven sử dụng như plugin.

**Packaging tùy biến** có thể do build extension cung cấp. Một số packaging không thuộc Maven core cần khai báo plugin/extension với **extensions=true** hoặc cơ chế tương ứng mới được Maven nhận diện. Nếu Maven báo **Unknown packaging**, cần kiểm tra extension và phiên bản; không thể khắc phục bằng cách chạy một phase khác.

## 5. Điều kiện chính xác để một phase có công việc

Có thể diễn đạt bằng ba câu hỏi liên tiếp:

1. **Phase có nằm trong phần lifecycle được gọi hay không?** Ví dụ **mvn compile** không xét **test**, **package** hay **verify** vì chúng đứng sau compile. Một goal gắn vào phase sau chưa chạy.
2. **Ở phase đó có goal được bind không?** Maven kết hợp binding mặc định của packaging với những execution được kích hoạt bởi cấu hình POM/parent/profile và cơ chế Maven liên quan. Nếu không có goal, phase đó không thực thi tác vụ plugin.
3. **Goal đã được bind có thực sự làm việc không?** Goal có thể chạy rồi báo “No sources to compile”, “No tests to run”, bỏ qua theo tham số **skip**, hoặc không tạo đầu ra mới. Điều này **khác** với phase không có goal.

Minh họa:

~~~text
mvn package (packaging jar)
       |
       +-- validate              không có goal mặc định ở phase này
       +-- generate-sources      không có goal mặc định
       +-- process-resources     resources:resources
       +-- compile               compiler:compile
       +-- process-test-resources resources:testResources
       +-- test-compile          compiler:testCompile
       +-- test                  surefire:test
       +-- prepare-package       không có goal mặc định
       +-- package               jar:jar
~~~

**Các phase không có goal không bị xem là lỗi.** Chúng là các điểm móc được thiết kế để plugin thêm nhiệm vụ khi dự án cần.

Ví dụ một dự án **jar** có **src/main/java** rỗng: Maven vẫn có binding **compiler:compile** ở phase **compile**, nhưng Compiler Plugin có thể thông báo không có nguồn để biên dịch. Đó là **goal đã được gọi nhưng không có đầu vào**, không phải Maven bỏ binding của phase compile.

Ví dụ khác: một dự án jar không có bài kiểm thử vẫn có **surefire:test** được gắn mặc định vào phase **test**; Surefire có thể báo không tìm thấy test và không chạy ca kiểm thử nào, tùy cấu hình. Việc build thành công **không chứng minh test đã thực sự chạy**.

## 6. Ví dụ Java 17 hoàn chỉnh: thêm công việc vào phase validate

Ta tạo một dự án **jar** có mã Java chạy được, sau đó gắn thêm goal **antrun:run** vào phase **validate**. Vì **validate** không có goal mặc định trong bảng jar, ví dụ này cho thấy một phase trống có thể được bổ sung công việc.

Cần JDK 17+ và Maven phù hợp. Tạo cấu trúc:

~~~text
binding-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── vn/example/binding/Main.java
~~~

### 6.1. Tệp pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>binding-demo</artifactId>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.2.0</version>
                <executions>
                    <execution>
                        <id>prove-validate-binding</id>
                        <phase>validate</phase>
                        <goals>
                            <goal>run</goal>
                        </goals>
                        <configuration>
                            <target>
                                <echo message="VALIDATE_GOAL_RAN"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích những gì được gắn:**

- **packaging=jar** tạo tập binding mặc định cho các phase như compile, test và package.
- **maven-compiler-plugin** có phiên bản rõ ràng để biên dịch Java theo thuộc tính **maven.compiler.release=17**.
- **maven-antrun-plugin** được khai báo cùng **executions/execution**; trong execution này, **phase=validate** và **goal=run** gắn một tác vụ vào validate.
- **echo** trong phần **target** là tác vụ Ant do Antrun Plugin thực thi. Dòng chứa **VALIDATE_GOAL_RAN** xuất hiện trong log khi goal tương ứng chạy thành công.

### 6.2. Tệp src/main/java/vn/example/binding/Main.java

~~~java
package vn.example.binding;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Maven lifecycle binding OK");
    }
}
~~~

### 6.3. Chạy từng phase để quan sát

Từ thư mục **binding-demo**:

~~~bash
mvn -B -ntp validate
~~~

Lệnh này chạy execution được gắn ở **validate** và log sẽ có thông báo **VALIDATE_GOAL_RAN**. Nhưng nó **chưa yêu cầu biên dịch** Java và **chưa đóng gói** JAR.

Tiếp theo:

~~~bash
mvn -B -ntp compile
~~~

Maven đi qua validate nên **Antrun cũng chạy**, sau đó tới process-resources và compile để tạo file **target/classes/vn/example/binding/Main.class**. **Không tự biên dịch test** vì lệnh dừng ở compile.

Cuối cùng:

~~~bash
mvn -B -ntp clean package
java -cp target/binding-demo-1.0.0.jar vn.example.binding.Main
~~~

Trong build, Maven chạy lifecycle clean trước, rồi tới phase package của default lifecycle. **Antrun tại validate được gọi lại**; compiler biên dịch mã; Surefire được gọi ở test và có thể không tìm thấy bài test; **jar:jar** tạo **target/binding-demo-1.0.0.jar**.

**Đầu ra chuẩn chính xác của riêng lệnh Java cuối cùng:**

~~~text
Maven lifecycle binding OK
~~~

Dùng **java -cp** thay cho **java -jar** vì POM này chưa khai báo **Main-Class** trong manifest. Đây là chương trình Java 17+ độc lập, không cần thư viện runtime bổ sung.

Khi dùng **mvn clean package**, nhìn log sẽ thấy goal hiển thị với dạng thường tương tự **maven-antrun-plugin:...:run (prove-validate-binding)**, **maven-compiler-plugin:...:compile (default-compile)** và **maven-jar-plugin:...:jar (default-jar)**. Tên execution/log cụ thể phụ thuộc phiên bản Maven/plugin; hãy đọc log thực tế thay vì phụ thuộc vào một chuỗi phiên bản cố định.

## 7. Đối chiếu với packaging pom

Bây giờ xét một **dự án độc lập khác** chỉ dùng làm parent hoặc aggregator, với POM:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>binding-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>
</project>
~~~

POM trên dùng tọa độ **vn.example:binding-parent:1.0.0** và packaging **pom**. Để dùng cấu trúc namespace/XSD quen thuộc nhất, có thể khai báo thêm **xsi:schemaLocation** và namespace đầy đủ như ví dụ mục 6; phần tử packaging mới là điểm cần đối chiếu ở đây.

Chạy trong thư mục chứa POM độc lập:

~~~bash
mvn -B -ntp package
~~~

Maven đi qua các phase đến package nhưng với packaging **pom**, theo binding mặc định **không có compiler:compile, surefire:test hoặc jar:jar**. Lệnh có thể trả về **BUILD SUCCESS** mà không sinh ra **target/binding-parent-1.0.0.jar**. Maven vẫn đã đọc và xây dựng mô hình POM; “không có goal package” **không phải lỗi**.

Nếu chạy:

~~~bash
mvn -B -ntp install
~~~

Packaging pom có binding **install:install** ở phase install nên POM artifact có thể được cài vào Maven local repository (khi build đạt và plugin hoạt động). Nếu POM này chứa **modules**, Maven reactor còn có thể tiếp tục build các module con với packaging riêng của chúng; vì vậy cần đọc log **theo từng module**, không kết luận rằng toàn bộ reactor sẽ không tạo JAR.

**Mấu chốt:** Packaging **pom** không cấm thêm goal tùy chỉnh ở **validate** hoặc **package**. Nếu khai báo một plugin execution ở các phase đó, phase sẽ có công việc dù mặc định packaging pom không bind goal tại đó.

## 8. Thêm công việc bằng plugin execution

Ngoài binding có sẵn theo packaging, ta có thể gắn một goal vào phase bằng phần **build/plugins** trong POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.2.0</version>
    <executions>
        <execution>
            <id>announce-verify</id>
            <phase>verify</phase>
            <goals>
                <goal>run</goal>
            </goals>
            <configuration>
                <target>
                    <echo message="VERIFY_GOAL_RAN"/>
                </target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Đây là **đoạn POM**, phải đặt bên trong **build/plugins** của một POM hợp lệ. Khi chạy **mvn verify**, Maven xét tới verify và thực thi **antrun:run** theo execution này. Khi chỉ chạy **mvn package**, execution ở verify **không chạy** vì verify nằm sau package.

Có ba điểm dễ nhầm:

1. **Khai báo plugin không tự có nghĩa mọi goal của plugin chạy.** Packaging có thể bind một số goal mặc định; muốn tác vụ tùy chỉnh theo lifecycle thì nên khai báo execution với goal/phase rõ ràng.
2. **Chỉ đưa plugin vào pluginManagement không tự tạo execution mới được kích hoạt.** PluginManagement chủ yếu quản lý version/cấu hình khi plugin được sử dụng hoặc có binding áp dụng; việc định nghĩa execution trong pluginManagement cần hiểu cơ chế kế thừa/áp dụng, không nên coi nó như một bước build tự chạy độc lập.
3. **Nếu một goal có default phase trong plugin descriptor**, execution khai báo goal mà không ghi **phase** có thể dùng default phase đó. Nếu goal không có default phase và không được bind bằng cách khác, nó **không tự chạy** trong lifecycle. Ghi **phase** tường minh giúp người đọc hiểu ý định, đặc biệt với goal tùy chỉnh.

Một plugin có thể chứa nhiều **execution** để chạy nhiều goal/phase. Mỗi execution nên có **id** duy nhất trong cùng plugin/POM. Không tạo hai khối **plugin** trùng groupId/artifactId trong cùng danh sách **build/plugins** chỉ để bổ sung một execution.

## 9. Một phase có nhiều goal: thứ tự thực thi

Một phase có thể chứa **0, 1 hoặc nhiều goal**. Khi có nhiều goal ở cùng phase, Maven phải chạy các goal theo thứ tự xác định.

Theo mô hình Maven 3 truyền thống và tài liệu lifecycle:

- Goal do **packaging** bind mặc định được chạy trước goal cấu hình thêm trong POM tại cùng phase.
- Goal được cấu hình trong các **plugin executions** tại phase đó chạy theo thứ tự khai báo tương ứng trong POM, có xét cơ chế hợp nhất từ parent/profile.
- Thứ tự chính xác của một build phức tạp có thể bị ảnh hưởng bởi inheritance, execution id và phiên bản Maven; **dùng log thực tế để xác nhận**.

Ví dụ muốn thêm một bước sau biên dịch ở phase **compile**, cần hiểu rằng **compiler:compile** do packaging jar bind mặc định thường thực hiện trước goal được thêm vào phase compile. Nhưng nếu plugin của bạn cần mã nguồn trước compile hoặc chỉ làm việc với file sau package, phase phù hợp có thể là **generate-sources**, **process-classes** hoặc **verify**, tùy đầu vào/đầu ra thực tế.

**Đừng gắn goal tùy ý vào phase sớm chỉ vì muốn nó chạy trước.** Điều đó có thể khiến goal truy cập file chưa được tạo, gây lỗi hoặc kết quả không ổn định giữa máy phát triển và CI.

## 10. Vì sao goal được gọi nhưng không làm gì rõ ràng?

Cần phân biệt **phase trống** với **goal chạy nhưng bỏ qua thao tác**:

| Hiện tượng | Diễn giải đúng |
| --- | --- |
| **mvn validate** trên POM jar không có execution riêng | Maven đọc/kiểm tra mô hình, nhưng phase validate mặc định không có plugin goal. |
| **mvn generate-sources** trên dự án jar không cấu hình code generation | Phase generate-sources có thể không có goal, dù lifecycle vẫn đi qua mốc đó. |
| **mvn compile** với src/main/java rỗng | **compiler:compile** vẫn được bind; plugin có thể báo không có gì để biên dịch. |
| **mvn test** với dự án không có test | **surefire:test** có thể được gọi nhưng không có test phù hợp để thực thi. |
| **mvn -DskipTests test** | Surefire có thể được gọi nhưng bỏ qua thực thi test theo cờ skip; test compilation vẫn có thể diễn ra. |
| **mvn package** với packaging pom | Không có goal package mặc định, nên không sinh JAR từ packaging pom. |
| **mvn verify** không cấu hình kiểm tra bổ sung | Maven chạy những goal đã bind ở các phase trước; bản thân phase verify có thể không có goal. |
| **mvn install** với packaging pom | **install:install** được bind, có thể cài POM vào repository cục bộ. |

**Không dùng “BUILD SUCCESS” làm bằng chứng mọi phase có tác vụ hay mọi bài test đã chạy.** Maven có thể hoàn tất yêu cầu trong khi những phase rỗng bị bỏ qua hoặc plugin không có đầu vào.

Cũng không nên cố buộc mọi phase phải có một goal. Một hệ build rõ ràng thường chỉ gắn goal ở những phase cần thiết cho đầu vào/đầu ra thật sự.

## 11. Lệnh kiểm tra binding và thứ tự thực tế

Trong dự án thực, nên xác nhận bằng bằng chứng từ Maven thay vì chỉ đoán theo packaging:

**Bước 1 — xem packaging và cấu hình nguồn:**

~~~bash
mvn --version
mvn help:effective-pom -Doutput=effective-pom.xml
~~~

**Effective POM** cho thấy phần cấu hình hiệu lực sau kế thừa/management/profile, nhưng không nên coi nó là một bảng in sẵn mọi binding mặc định. **Packaging-to-lifecycle mapping** thuộc Maven core và các extension, do đó log thực thi hoặc tài liệu mapping của phiên bản Maven vẫn là bằng chứng cần thiết.

**Bước 2 — chạy tới đúng phase và đọc goal xuất hiện trong log:**

~~~bash
mvn -B -ntp validate
mvn -B -ntp compile
mvn -B -ntp package
~~~

Các lệnh trên minh họa các mốc kiểm tra **riêng biệt**. Nếu đã có output từ lượt chạy trước, Maven có thể tái sử dụng file và log không phản ánh sự khác biệt giữa chạy lại và build sạch. Khi cần loại bỏ ảnh hưởng output cũ, chọn:

~~~bash
mvn -B -ntp clean verify
~~~

**Bước 3 — chỉ khi cần điều tra sâu, bật debug:**

~~~bash
mvn -X -B package
~~~

Log debug cho biết plugin, execution, cấu hình và nhiều chi tiết khác; có thể dài, nên lọc đúng phần cần xem và kiểm tra thông tin môi trường trước khi chia sẻ. Với dự án có parent/profile, dùng thêm **mvn help:active-profiles** nếu cần đối chiếu các profile đang kích hoạt.

**Bước 4 — kiểm tra đúng module trong reactor:** ở multi-module build, mỗi module có packaging và plugin execution riêng. Dùng các lệnh có chọn module như **mvn -pl app package** khi biết đúng tên module và cấu trúc reactor. Không lấy log build của parent packaging pom để suy diễn binding của module con packaging jar.

**Bước 5 — đọc tài liệu mapping tương ứng:** tài liệu Apache Maven **Introduction to the Build Lifecycle**, **Lifecycles Reference** và **Plugin Bindings for Default Lifecycle Reference** cung cấp danh sách phase/binding. Khi dùng Maven 3.x, tham chiếu mapping của Maven 3; với Maven 4, dùng tài liệu của phiên bản đang chạy vì cấu trúc lifecycle và mapping có thể thay đổi.

## 12. Những lỗi thiết kế thường gặp

**Nhầm phase với một lệnh cụ thể.** Viết “phase compile luôn chạy compiler:compile” sẽ sai cho packaging pom không có binding đó mặc định. Câu đúng là: **compiler:compile được bind mặc định tới compile đối với những packaging như jar/war**.

**Tưởng phase trống làm build thất bại.** Phase trống là bình thường; Maven tiếp tục các phase tiếp theo nếu được yêu cầu. Muốn phase có công việc, gắn một goal phù hợp qua packaging hoặc cấu hình plugin.

**Tưởng goal có tên gần giống phase sẽ tự chạy.** Tên **jar:jar** không tự chạy chỉ vì POM có plugin jar. Maven cần mapping từ packaging hoặc execution. Gọi goal trực tiếp như **mvn jar:jar** cũng khác gọi cả phase **mvn package**: goal trực tiếp không mặc nhiên chạy toàn bộ các phase trước nó.

**Tưởng pluginManagement luôn kích hoạt plugin.** Nó chủ yếu quản lý version/cấu hình; kiểm tra xem goal có thực sự được bind bởi packaging hoặc được khai báo trong executions phù hợp.

**Gọi integration-test trực tiếp để kiểm tra tất cả.** Một số plugin triển khai môi trường ở **pre-integration-test**, chạy test ở **integration-test** và dọn môi trường ở **post-integration-test**. Gọi riêng **integration-test** có thể chưa tới bước cleanup/verify và để lại môi trường còn hoạt động. Thường nên gọi **verify** cho chu trình integration test đã được cấu hình.

**Đọc BUILD SUCCESS rồi khẳng định test đã chạy.** Có thể không có test, test bị skip hoặc packaging pom không bind Surefire. Cần đọc goal xuất hiện, số ca kiểm thử và báo cáo test.

**Chỉ đổi packaging để “thêm tính năng”.** Chuyển từ pom sang jar có thể làm Maven tạo mục tiêu biên dịch/đóng gói cho module vốn chỉ là parent; chuyển từ jar sang war thay đổi artifact đích và có yêu cầu cấu trúc riêng. Hãy chọn packaging theo mục đích module, sau đó thêm plugin đúng nơi cần thiết.

**Ghi trực tiếp các tên phiên bản plugin vào kỳ vọng log.** Version plugin có thể đến từ Super POM, pluginManagement hoặc parent. Giữ version được quản lý tập trung khi cần tính tái lập; đối chiếu bằng log Maven đang chạy.

**Cùng plugin bị khai báo nhiều lần trong build/plugins.** Maven 3 có thể cảnh báo, Maven 4 nghiêm ngặt hơn. Gộp cấu hình/execution vào một khai báo plugin.

## 13. Quy trình xác định một phase có công việc hay không

Khi nhận một dự án Maven mới, đi theo thứ tự:

1. **Xác định POM, packaging và module** đang được build. Nếu không khai báo packaging, mặc định là jar. Kiểm tra parent và extension nếu có.
2. **Xác định lifecycle/phase đã yêu cầu**, ví dụ package hay verify; đánh dấu phase nào nằm trước điểm dừng.
3. **Tra binding mặc định của packaging** đúng phiên bản Maven, nhất là các phase compile, test và package.
4. **Kiểm tra plugin executions bổ sung** từ POM, parent, profile; phân biệt pluginManagement với plugin được sử dụng.
5. **Chạy Maven và đọc log goal/execution**. Phase không có goal khác với goal chạy nhưng không có source/test hoặc bị skip.
6. **Kiểm tra output và test report thực tế** theo nhu cầu. Không dùng sự tồn tại của file cũ làm bằng chứng lượt chạy hiện tại đã sinh file.
7. **Điều chỉnh binding có mục đích** nếu thiếu công việc: chọn phase mà đầu vào đã sẵn sàng, pin phiên bản plugin, giữ execution id rõ ràng và kiểm tra bằng **mvn clean verify**.

Một dự án Maven dễ bảo trì là dự án mà **mỗi plugin goal có lý do để chạy tại đúng phase**, và các thao tác mặc định theo packaging được tận dụng khi phù hợp.

### Tài liệu chính thức

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Apache Maven — POM Reference (Packaging)](https://maven.apache.org/pom.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven 3 — Lifecycles Reference](https://maven.apache.org/ref/3-LATEST/maven-core/lifecycles.html)
- [Apache Maven 3 — Plugin Bindings for Default Lifecycle](https://maven.apache.org/ref/3-LATEST/maven-core/default-bindings.html)
