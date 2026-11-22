# Hợp nhất cấu hình execution khi kế thừa parent POM trong Maven

## 1. Vấn đề thực tế: tại sao goal chạy hai lần hoặc không chạy ở child?

Trong một dự án Maven nhiều module, tổ chức thường đặt những công việc chung vào `pom.xml` của parent. Ví dụ, parent dùng `maven-antrun-plugin` để thực hiện kiểm tra ở phase `validate`, rồi module `app` muốn thay thông điệp hoặc điều kiện của kiểm tra đó. Nếu module thêm một execution với **ID khác**, Maven có thể giữ execution cũ và bổ sung execution mới: cùng một goal chạy hai lần. Nếu module khai **cùng ID**, Maven có thể hợp nhất cấu hình và chỉ có một execution hiệu lực. Nếu parent gắn `<inherited>false</inherited>`, một execution có thể hoàn toàn không truyền xuống child.

Để kiểm soát hiện tượng này, bạn cần hiểu **POM inheritance**, **plugin execution**, **execution ID** và **XML configuration merge**. Chúng là bốn lớp khác nhau nhưng thường xuất hiện cùng lúc.

Mục tiêu của bài học:

1. Giải thích Maven ghép execution từ parent và child theo ID thế nào.
2. Phân biệt thêm execution có ID mới với sửa execution kế thừa có ID cũ.
3. Xác định khi nào dùng `<inherited>false</inherited>` ở plugin level hoặc execution level.
4. Hiểu `combine.self="override"`, `combine.children="append"` và default XML merge.
5. Phân biệt `build/plugins` với `build/pluginManagement`, cũng như inheritance với aggregation.
6. Chạy lab đầy đủ gồm parent POM, child POM, Maven Antrun Plugin và class Java 17.
7. Dùng `help:effective-pom -Dverbose=true` để kiểm tra phase, goals, configuration sau khi merge.
8. Tránh lệnh build chạy trùng tác vụ, gây side effects, hoặc kế thừa những execution chỉ dành cho parent.

Điều quan trọng nhất: **cùng ID không có nghĩa child tự tạo thêm một lần chạy**, và **khác ID không có nghĩa child tự ghi đè execution cũ**. Hãy xem effective POM và log thực thi để xác minh.

## 2. Những khái niệm nền tảng

### 2.1. Plugin và goal

Maven plugin là artifact chứa một hoặc nhiều tác vụ. Chẳng hạn:

~~~text
org.apache.maven.plugins:maven-antrun-plugin:3.1.0
~~~

Plugin này cung cấp goal `antrun:run` để thực hiện Ant tasks. Tương tự, Maven Compiler Plugin cung cấp `compiler:compile` và `compiler:testCompile`. Một **goal** có thể được gọi trực tiếp bằng CLI hoặc được gắn vào lifecycle phase.

Ví dụ:

~~~bash
mvn compile
mvn org.apache.maven.plugins:maven-compiler-plugin:3.14.0:compile
~~~

Lệnh thứ nhất gọi **phase compile** của default lifecycle; Maven chạy những goals được bind vào các phase cho đến `compile`. Lệnh thứ hai yêu cầu gọi **goal compiler:compile trực tiếp**. Hai cách không đồng nghĩa về toàn bộ các phase/goals được chạy.

### 2.2. Execution và execution ID

Một execution khai goal, phase và những tham số cần dùng:

~~~xml
<execution>
    <id>announce-build</id>
    <phase>validate</phase>
    <goals>
        <goal>run</goal>
    </goals>
    <configuration>
        <target>
            <echo message="BUILD START"/>
        </target>
    </configuration>
</execution>
~~~

Đoạn trên đặt trong `<build><plugins><plugin><executions>`. Nó chưa phải một POM hoàn chỉnh.

| Thành phần | Vai trò |
| --- | --- |
| `<id>` | Định danh execution; dùng khi merge các execution kế thừa và hiển thị log |
| `<phase>` | Phase gắn execution trong lifecycle |
| `<goals><goal>` | Goal(s) sẽ chạy trong execution |
| `<configuration>` | Các tham số áp dụng riêng cho execution |
| `<inherited>` | Cho phép hoặc chặn kế thừa execution sang child |

`<id>` không phải tên plugin. Một plugin có thể có nhiều execution IDs; hai plugin khác nhau có thể có execution cùng ID mà không có nghĩa Maven sẽ gộp chúng.

Theo Maven Model, execution không có `<id>` được xem là có ID mặc định `default`. Vì vậy trong **cùng một plugin, cùng một POM**, đừng tạo nhiều execution không khai ID rồi mong Maven tự cấp định danh khác nhau. Hãy dùng ID có ý nghĩa và duy nhất.

### 2.3. Parent khác aggregator

`<parent>` trong child làm Maven biết cần **kế thừa** cấu hình:

~~~xml
<parent>
    <groupId>dev.example</groupId>
    <artifactId>execution-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

Trong khi đó, `<modules>` ở root chỉ đưa modules vào **reactor**:

~~~xml
<modules>
    <module>app</module>
</modules>
~~~

Một root có thể là parent kiêm aggregator, nhưng **aggregation không tự tạo inheritance**. Nếu `app/pom.xml` được liệt kê trong `<modules>` mà không khai đúng `<parent>`, app không tự nhận các executions của root.

Đây là nguồn gây hiểu nhầm phổ biến khi `mvn validate` từ root in một thông điệp mà bạn tưởng nó xuất phát từ child. Có thể đó là execution **của chính parent project**.

## 3. Quy tắc hợp nhất theo execution ID

### 3.1. ID khác nhau: các executions thường cùng tồn tại

Parent khai:

~~~xml
<execution>
    <id>parent-check</id>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <configuration>
        <target><echo message="PARENT CHECK"/></target>
    </configuration>
</execution>
~~~

Child khai dưới **cùng plugin**:

~~~xml
<execution>
    <id>child-check</id>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <configuration>
        <target><echo message="CHILD CHECK"/></target>
    </configuration>
</execution>
~~~

Nếu plugin và các executions được kế thừa/sử dụng phù hợp, effective POM của child có cả `parent-check` lẫn `child-check`. Vì đều bind vào `validate`, hai mục có thể chạy trong cùng lượt `mvn validate`.

Mẫu nội dung output:

~~~text
PARENT CHECK
CHILD CHECK
~~~

Đây là **chuỗi echo cần tìm trong log**, không phải toàn bộ stdout; Ant/Maven thường có tiền tố `[echo]` và các header plugin goals.

Theo hướng dẫn chính thức *Guide to Configuring Plug-ins*, khi các executions khác ID cùng được áp dụng thì chúng được ghép theo thứ tự hierarchy (parent trước child). Thứ tự của toàn bộ goals trong một phase còn chịu ảnh hưởng bởi packaging bindings, nhiều plugin khác và execution plan, vì vậy không dựa vào thứ tự một dòng log để thiết kế một chuỗi phụ thuộc phức tạp.

### 3.2. ID trùng: child điều chỉnh execution kế thừa

Parent:

~~~xml
<execution>
    <id>shared-check</id>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <configuration>
        <target>
            <echo message="FROM PARENT"/>
        </target>
    </configuration>
</execution>
~~~

Child:

~~~xml
<execution>
    <id>shared-check</id>
    <configuration>
        <target combine.self="override">
            <echo message="FROM CHILD"/>
        </target>
    </configuration>
</execution>
~~~

Maven nhận diện `shared-check` theo ID trong cùng plugin và **hợp nhất thành một execution logic**. Child có cấu hình target mới. Vì `combine.self="override"` áp tại `target`, target kế thừa được thay trọn bằng target của child.

Trong ví dụ này, child không khai `phase` hoặc `goals`, nên các trường đó được giữ từ nguồn parent theo model merge; effective execution vẫn gắn `antrun:run` vào `validate`. Khi chạy child, bạn kỳ vọng `FROM CHILD`, không phải một execution độc lập khác in `FROM PARENT`.

Một số tài liệu diễn đạt execution cùng ID là “overwritten by child configuration”. **Không nên hiểu điều này là toàn bộ trường của execution parent bị xóa**. Maven có cơ chế merge fields/XML: trường nào child xác định có thể ưu tiên, phần parent chưa bị thay vẫn có thể xuất hiện. Đọc effective POM để kết luận chính xác.

### 3.3. Cùng ID nhưng muốn đổi phase

Child có thể sửa:

~~~xml
<execution>
    <id>shared-check</id>
    <phase>verify</phase>
</execution>
~~~

Điều này thể hiện ý định chuyển execution kế thừa từ `validate` sang `verify`, không thêm execution mới. `phase` được child cung cấp, còn phần `goals` và cấu hình khác có thể được giữ theo merge.

Khi kiểm tra:

~~~bash
mvn validate
mvn verify
~~~

Execution không còn được kỳ vọng chạy ở `validate` trong trường hợp phase đã được ghi đè thành `verify`. Nhưng `verify` đi qua các phase trước, vì vậy những execution khác ở `validate` vẫn có thể chạy trong lệnh `mvn verify`.

### 3.4. ID chỉ cần duy nhất trong một plugin

Hai plugin khác nhau có thể dùng `<id>generate-code</id>` mà không bị merge với nhau. Cơ chế nhận diện execution xét **plugin coordinate** và ID tương ứng. Nếu tìm `generate-code` trong effective POM, hãy ghi đủ:

~~~text
plugin: org.apache.maven.plugins:maven-antrun-plugin
execution id: generate-code
phase: validate
goal: run
~~~

Với một plugin, nhiều execution cùng ID **trong cùng một POM** không phải cách tạo hai lần chạy; có thể làm validation báo duplicate ID. ID trùng giữa **parent và child** lại được thiết kế để phục vụ inheritance merge.

## 4. Kế thừa hoặc không kế thừa: inherited ở hai cấp

### 4.1. `inherited=false` tại một execution

Parent:

~~~xml
<execution>
    <id>parent-only</id>
    <inherited>false</inherited>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <configuration>
        <target><echo message="ONLY IN PARENT"/></target>
    </configuration>
</execution>
~~~

Execution `parent-only` vẫn có thể chạy ở **parent project**. Nhưng Maven không truyền execution đó xuống child khi xử lý inheritance. Đây là cách phù hợp cho:

- Một tác vụ kiểm tra file chỉ tồn tại ở root.
- Sinh file metadata phục vụ parent/aggregator.
- Tác vụ chỉ cần chạy một lần trong một reactor.
- Những công việc có side effects nên tránh thực thi lặp trên mọi module.

**Cảnh báo:** `inherited=false` không có nghĩa “không chạy trong parent”. Nó chỉ điều khiển **truyền xuống POM con**.

### 4.2. `inherited=false` tại plugin level

Parent có thể khai:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <inherited>false</inherited>
    <executions>
        <!-- Các execution dành riêng cho parent -->
    </executions>
</plugin>
~~~

Cách này chặn inheritance của **plugin declaration** xuống child, rộng hơn nhiều so với `inherited=false` trên một execution. Nếu bạn muốn child kế thừa `shared-check` nhưng không kế thừa `parent-only`, hãy đặt `inherited=false` ở **parent-only execution** chứ không ở toàn plugin.

| Vị trí | Kết quả chính |
| --- | --- |
| `plugin/inherited=false` | Plugin declaration của parent không được kế thừa theo cơ chế thông thường |
| `plugin/executions/execution/inherited=false` | Chỉ execution tương ứng không được truyền xuống child |
| Không khai inherited | Mặc định `true` trong Maven Model |

Khi child có plugin declaration riêng trùng tọa độ, Maven còn có cơ chế quản lý/merge khác cần kiểm tra. Đừng suy từ một flag đơn lẻ rằng child không thể sử dụng plugin đó nữa.

### 4.3. Quan sát reactor log đúng cách

Nếu root vừa là parent vừa là aggregator:

~~~bash
mvn -B -ntp -f pom.xml validate
~~~

có thể chạy các executions trên project root rồi tới child. Thông điệp `ONLY IN PARENT` xuất hiện trong log tổng thể **không** chứng minh execution bị kế thừa sang app.

Để tập trung kiểm tra child:

~~~bash
mvn -B -ntp -f app/pom.xml validate
~~~

Hãy xác nhận log hiển thị `@ app`, execution ID và message; hoặc đọc effective POM của app.

## 5. Hợp nhất các phần tử XML trong configuration

Hợp nhất **execution theo ID** và hợp nhất **configuration XML** là hai lớp khác nhau. Cấu hình plugin/goal được Maven ghép theo tên phần tử XML, với những quy tắc mặc định và hai thuộc tính đặc biệt.

### 5.1. Default merge: phần tử child ưu tiên, các phần khác có thể được giữ

Parent (đây là cấu trúc minh họa của một plugin giả định, **không phải POM runnable**):

~~~xml
<configuration>
    <options>
        <strict>true</strict>
        <language>en</language>
    </options>
    <items>
        <item>parent-a</item>
        <item>parent-b</item>
    </items>
</configuration>
~~~

Child:

~~~xml
<configuration>
    <options>
        <language>vi</language>
        <trace>true</trace>
    </options>
    <items>
        <item>child-a</item>
    </items>
</configuration>
~~~

Sau default merge, phần XML tiêu biểu có thể là:

~~~xml
<configuration>
    <options>
        <strict>true</strict>
        <language>vi</language>
        <trace>true</trace>
    </options>
    <items>
        <item>child-a</item>
    </items>
</configuration>
~~~

`strict` còn từ parent, `language` dùng child, `trace` được thêm. Đối với list có các phần tử `item` lặp lại, **không có bảo đảm mặc định là toàn bộ list parent luôn được nối thêm**. Maven merge theo XML, không tự suy ý nghĩa danh sách của plugin.

### 5.2. `combine.self="override"` thay cả phần tử

Nếu child muốn bỏ toàn bộ `options` của parent:

~~~xml
<configuration>
    <options combine.self="override">
        <language>vi</language>
    </options>
</configuration>
~~~

Kết quả có phần tử `options` chỉ chứa `language=vi` của child; không còn `strict` từ parent trong phần tử đó.

Đây là lý do ví dụ Antrun dùng:

~~~xml
<configuration>
    <target combine.self="override">
        <echo message="CHILD OVERRIDES COMMON"/>
    </target>
</configuration>
~~~

Với một `target` chứa nhiều Ant tasks, **thay trọn target** thường dễ dự đoán hơn việc vô tình merge nhiều thẻ `echo` cùng tên.

### 5.3. `combine.children="append"` nối danh sách

Parent:

~~~xml
<configuration>
    <items>
        <item>parent-a</item>
        <item>parent-b</item>
    </items>
</configuration>
~~~

Child:

~~~xml
<configuration>
    <items combine.children="append">
        <item>child-a</item>
    </items>
</configuration>
~~~

Kết quả minh họa:

~~~xml
<configuration>
    <items combine.children="append">
        <item>parent-a</item>
        <item>parent-b</item>
        <item>child-a</item>
    </items>
</configuration>
~~~

Dùng append khi plugin thật sự chấp nhận phần tử dạng danh sách cần nối. Với Ant tasks, output files, resources hoặc includes/excludes, việc nối có thể tạo side effects; cần xác minh kết quả.

### 5.4. Quy tắc và giới hạn combine

- `combine.self` hỗ trợ `merge` (mặc định) hoặc `override`.
- `combine.children` hỗ trợ `merge` (mặc định) hoặc `append`.
- Nếu cùng một phần tử dùng cả override và append, **override thắng**.
- Thuộc tính áp dụng cho **phần tử được đánh dấu**, không tự lan tới mọi phần tử con.
- Những thuộc tính này có thể **được kế thừa từ parent**, ảnh hưởng tới cả grandchild.
- `combine.*` **không phải** cơ chế cho execution IDs. Muốn thêm execution dùng ID mới; muốn sửa execution dùng ID cũ rồi merge configuration ở đúng nơi.

Cơ chế này được Maven POM Reference mô tả cho cấu hình plugin; plugin sẽ diễn giải XML sau khi Maven ghép. Maven không tự biết các phần tử mang semantics “merge by key”, “concat tasks” hay “replace rule” trừ khi model/plugin hỗ trợ.

## 6. Plugin-level và execution-level configuration

Trong một plugin có hai nơi cấu hình:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>

    <configuration>
        <!-- Tham số chung cho plugin -->
    </configuration>

    <executions>
        <execution>
            <id>one</id>
            <phase>validate</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <!-- Tham số riêng của execution one -->
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

Cấp `plugin/configuration` thường đặt mặc định chung, còn `execution/configuration` áp cho goal trong execution đó. Khi Maven thực thi, các tham số có thể được ghép thêm với plugin descriptor, system/user properties và các ngữ cảnh liên quan.

Nếu child muốn sửa **chỉ execution `one`**, nên khai cùng ID trong `executions` và chỉnh `execution/configuration`. Nếu child đặt tham số ở `plugin/configuration`, thay đổi có thể ảnh hưởng các execution khác của plugin.

Khi kiểm tra, luôn ghi đầy đủ đường dẫn:

~~~text
project
  build
    plugins
      plugin[artifactId=maven-antrun-plugin]
        executions
          execution[id=one]
            phase
            goals
            configuration
~~~

Không đọc `<configuration>` ở một cấp rồi suy rằng nó có tác động y hệt ở mọi cấp.

## 7. pluginManagement và cách execution được áp dụng

Parent có thể quản lý plugin thay vì trực tiếp kích hoạt nó:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>
                <executions>
                    <execution>
                        <id>managed-announce</id>
                        <phase>validate</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <echo message="MANAGED ANNOUNCE"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

**Chỉ có khai báo trên không đảm bảo `antrun:run` tự thực thi ở mọi child**. `pluginManagement` lưu thông tin version/config/executions để áp dụng khi plugin được sử dụng. Child có thể chọn dùng Antrun:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-antrun-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

Trong ngữ cảnh đó Maven có thể áp managed version/execution, và child vẫn có thể khai execution cùng ID để điều chỉnh. Nhưng khi không có việc sử dụng plugin/binding phù hợp, không nên kỳ vọng managed execution tự chạy.

**Một ngoại lệ cần biết:** một số plugins được packaging bind mặc định, ví dụ Compiler Plugin đối với dự án `jar`. `pluginManagement` vẫn có thể quản lý chúng khi Maven sử dụng chúng qua lifecycle binding. Vì thế câu “pluginManagement chỉ có tác dụng nếu child khai plugin dưới build/plugins” là một cách nói quá tuyệt đối.

| Cấu hình | Tác dụng |
| --- | --- |
| `parent build/plugins`, `inherited=true` | Plugin và executions có thể được kế thừa để chạy ở child |
| `parent build/pluginManagement` | Chỉ quản lý version/config/executions cho plugin khi được sử dụng |
| `child build/plugins` cùng tọa độ plugin | Có thể nhận/ghi đè phần quản lý hoặc kế thừa |
| `execution inherited=false` | Execution đó không được kế thừa |
| `plugin inherited=false` | Khai báo plugin không được kế thừa theo cách thông thường |

## 8. Lab hoàn chỉnh: một parent và một child Java 17

Mục đích lab là tạo **thông điệp khác nhau cho các executions**, để có bằng chứng trực tiếp về việc execution nào chạy ở project nào.

### 8.1. Điều kiện và cấu trúc

Yêu cầu:

- JDK 17 trở lên; Maven chạy được bằng `mvn -version`.
- Maven 3.9.x (hoặc bản đã kiểm tra tương thích) và kết nối tới artifact repositories cho lần tải plugin đầu.
- Không cần database, Docker, Spring Boot hay tài khoản dịch vụ ngoài.

Cấu trúc:

~~~text
execution-inheritance-lab/
├── pom.xml
└── app/
    ├── pom.xml
    └── src/
        └── main/
            └── java/
                └── dev/
                    └── example/
                        └── App.java
~~~

Root `pom.xml` là parent kiêm aggregator với `packaging=pom`. Child `app` khai `<parent>` trỏ lên root.

### 8.2. Parent POM đầy đủ

Tạo `execution-inheritance-lab/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>execution-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>app</module>
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
                    <version>3.14.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-clean-plugin</artifactId>
                    <version>3.4.1</version>
                </plugin>
            </plugins>
        </pluginManagement>

        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>
                <version>3.1.0</version>

                <executions>
                    <!-- Execution dùng chung nhưng child sẽ thay target -->
                    <execution>
                        <id>common-banner</id>
                        <phase>validate</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <echo message="PARENT COMMON"/>
                            </target>
                        </configuration>
                    </execution>

                    <!-- Execution chia sẻ nguyên vẹn -->
                    <execution>
                        <id>shared-hook</id>
                        <phase>validate</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <echo message="PARENT SHARED HOOK"/>
                            </target>
                        </configuration>
                    </execution>

                    <!-- Execution chỉ chạy trên project parent -->
                    <execution>
                        <id>parent-only</id>
                        <inherited>false</inherited>
                        <phase>validate</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <echo message="PARENT ONLY"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Phân tích:

1. `common-banner` có ID ổn định, phase `validate`, goal `run` và target in `PARENT COMMON`.
2. `shared-hook` cùng plugin nhưng ID khác, được kế thừa mặc định.
3. `parent-only` đặt `inherited=false` ở **execution** nên không truyền sang child.
4. `pluginManagement` quản lý Compiler/JAR/Clean versions cho build Java; đó không phải các executions Antrun.
5. Parent packaging `pom` có thể chạy **execution Antrun được bind vào validate**, dù không có Java source tại root.

### 8.3. Child POM đầy đủ

Tạo `execution-inheritance-lab/app/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>execution-parent</artifactId>
        <version>1.0.0</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-antrun-plugin</artifactId>

                <executions>
                    <!-- Cùng ID với parent: thay toàn bộ target -->
                    <execution>
                        <id>common-banner</id>
                        <configuration>
                            <target combine.self="override">
                                <echo message="CHILD OVERRIDES COMMON"/>
                            </target>
                        </configuration>
                    </execution>

                    <!-- ID khác: execution mới do child bổ sung -->
                    <execution>
                        <id>child-only</id>
                        <phase>validate</phase>
                        <goals><goal>run</goal></goals>
                        <configuration>
                            <target>
                                <echo message="CHILD EXTRA"/>
                            </target>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Lý do cố ý không khai `<phase>` hoặc `<goals>` trong `common-banner` của child: chúng sẽ được giữ từ execution parent cùng ID sau merge. Điều chỉnh chỉ nằm trong `target`.

Không có `<version>` ở plugin Antrun trong child vì version đã có ở parent. `child-only` có ID riêng và đầy đủ phase/goals, vì đây là execution mới chứ không phải phần mở rộng của execution parent.

### 8.4. File Java chạy được

Tạo `app/src/main/java/dev/example/App.java`:

~~~java
package dev.example;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println("Execution inheritance demo: " + (7 + 5));
    }
}
~~~

Lệnh từ thư mục root `execution-inheritance-lab`:

~~~bash
mvn -B -ntp -f app/pom.xml clean package
java -cp app/target/classes dev.example.App
~~~

Với JDK 17+ và build thành công, **stdout chính xác từ lệnh Java cuối**:

~~~text
Execution inheritance demo: 12
~~~

Câu lệnh `mvn clean package` còn in log lifecycle, echo từ Antrun và các goal khác. Không coi dòng Java ở trên là toàn bộ Maven stdout.

### 8.5. Kiểm chứng execution sau merge chỉ trên child

Từ root lab:

~~~bash
mvn -B -ntp -f app/pom.xml validate
~~~

Các thông điệp bạn cần tìm trong log:

~~~text
CHILD OVERRIDES COMMON
PARENT SHARED HOOK
CHILD EXTRA
~~~

Ba thông điệp có thể được in với tiền tố `[echo]` và các header của plugin. **Không có thông điệp PARENT COMMON ở execution cùng ID** và **không có PARENT ONLY trong project child**.

Đối chiếu:

| ID | Nguồn | Trong effective POM child? | Hiệu ứng |
| --- | --- | --- | --- |
| `common-banner` | Parent + child cùng ID | Có, một execution | `CHILD OVERRIDES COMMON` |
| `shared-hook` | Chỉ parent | Có | `PARENT SHARED HOOK` |
| `parent-only` | Parent, inherited=false | Không | Không chạy ở child |
| `child-only` | Chỉ child | Có | `CHILD EXTRA` |

Đây là bằng chứng quan sát trực tiếp của **same ID merge**, **different ID addition** và **inherited=false**.

### 8.6. So với build reactor từ root

Chạy:

~~~bash
mvn -B -ntp -f pom.xml validate
~~~

Lệnh này có thể xử lý **project parent và module child** trong reactor. Trong block log của parent, bạn có thể thấy:

~~~text
PARENT COMMON
PARENT SHARED HOOK
PARENT ONLY
~~~

Trong block của app, tìm:

~~~text
CHILD OVERRIDES COMMON
PARENT SHARED HOOK
CHILD EXTRA
~~~

Vì `PARENT ONLY` được thiết kế để chạy ở parent nên sự xuất hiện của nó trong **toàn bộ log reactor** không chứng minh nó đã lọt vào child. Luôn xác nhận tên project cạnh execution header.

### 8.7. Xuất effective POM của child

Tại root lab:

~~~bash
mvn -B -ntp -f app/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=app-effective-pom.xml
~~~

`help:effective-pom` xuất mô hình sau inheritance/profile interpolation. `-Dverbose=true` (Help Plugin hỗ trợ từ 3.2.0) thêm XML comments về nguồn phần tử. Đường dẫn `app-effective-pom.xml` là tương đối; vị trí output phụ thuộc ngữ cảnh goal/project, nên kiểm tra log hoặc dùng đường dẫn tuyệt đối khi cần.

Trong file XML, tìm:

~~~text
project
  build
    plugins
      plugin[maven-antrun-plugin]
        executions
          common-banner
          shared-hook
          child-only
~~~

`common-banner` có phase `validate` và goal `run` từ parent, nhưng `target` in `CHILD OVERRIDES COMMON`. `parent-only` không nằm trong effective executions của app. Nếu file chứa plugin đó trong `pluginManagement`, đừng nhầm với danh sách plugin thực sự được dùng ở `build/plugins`.

### 8.8. Nhận diện execution header

Ở Maven 3.9.x, một số header log thường có dạng:

~~~text
--- maven-antrun-plugin:3.1.0:run (common-banner) @ app ---
--- maven-antrun-plugin:3.1.0:run (shared-hook) @ app ---
--- maven-antrun-plugin:3.1.0:run (child-only) @ app ---
~~~

Đây là **mẫu nhận diện**, không phải kết quả nguyên văn bắt buộc. Logger, console style, Maven core và plugin version có thể đổi cách hiển thị. Nội dung cần xác nhận là **plugin coordinate, execution ID và project đang chạy**.

## 9. Các thí nghiệm thay đổi có kiểm soát

### 9.1. Đổi ID của child nhưng không thêm phase/goal

Trong `app/pom.xml` đổi `<id>common-banner</id>` thành `<id>different-banner</id>` mà không đổi cấu hình khác.

Khi đó Maven không còn ghép với execution `common-banner` của parent. Parent `common-banner` tiếp tục được kế thừa; execution `different-banner` mới **chưa có phase và goals** trong POM child, nên không thể tự kết luận rằng nó sẽ chạy trong `mvn validate`.

**Đây là một bẫy:** khác ID tạo thêm execution model, nhưng việc nó được thực thi còn phụ thuộc phase/goal. Nếu muốn chứng minh hai lần chạy, bổ sung đầy đủ:

~~~xml
<execution>
    <id>different-banner</id>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <configuration>
        <target><echo message="CHILD SECOND BANNER"/></target>
    </configuration>
</execution>
~~~

Khi đó parent `common-banner` và child `different-banner` là hai execution độc lập, đều bind vào `validate`; thông thường sẽ có cả `PARENT COMMON` và `CHILD SECOND BANNER`.

### 9.2. Giữ ID nhưng chuyển phase

Trong execution `common-banner` của child, thêm:

~~~xml
<phase>verify</phase>
~~~

Giữ `<id>common-banner</id>` và phần target mới. Khi xem effective POM, bạn kỳ vọng execution được chuyển sang phase `verify`. Chạy `mvn -f app/pom.xml validate` để thấy riêng execution này không chạy ở `validate`; chạy `mvn -f app/pom.xml verify` để thấy execution chạy khi đến `verify`. Những execution khác ở validate vẫn chạy khi Maven tiến tới verify.

### 9.3. Bỏ combine.self

Đổi:

~~~xml
<target combine.self="override">
    <echo message="CHILD OVERRIDES COMMON"/>
</target>
~~~

thành:

~~~xml
<target>
    <echo message="CHILD OVERRIDES COMMON"/>
</target>
~~~

Khi merge mặc định, Maven ghép cấu trúc XML theo tên phần tử. Việc có các thẻ `echo` cùng tên trong Ant target có thể cho kết quả không như bạn đoán. Hãy **xuất effective POM rồi chạy mục tiêu**; không dùng thay đổi này trong production nếu chưa xác minh side effects. `combine.self="override"` trong lab làm rõ ý định **thay toàn bộ target**.

### 9.4. Bỏ inherited=false ở parent-only

Từ parent, xóa `<inherited>false</inherited>` trong execution `parent-only`. Nó trở lại trạng thái inherited mặc định, có thể xuất hiện và chạy ở child khi `validate`. Sau khi hoàn nguyên, execution lại bị chặn ở child nhưng vẫn có thể chạy ở parent.

### 9.5. Đưa toàn plugin vào pluginManagement

Thử chuyển entry `maven-antrun-plugin` ở parent từ `build/plugins` vào `build/pluginManagement/plugins`. Lúc đó parent chỉ **quản lý** plugin; không còn tự khai một build plugin trực tiếp để chạy Antrun goals trong project parent. Vì child lab **đang khai Antrun** ở `build/plugins`, các managed settings/executions có thể được áp dụng vào plugin được dùng ở child.

Nếu bỏ luôn entry Antrun khỏi `build/plugins` của child, không được mặc định `antrun:run` sẽ tự chạy ở `validate`. Đây là kiểm chứng rõ sự khác nhau giữa **pluginManagement** và **plugins thực sự được sử dụng**.

### 9.6. Khai inherited=false ở plugin level

Khi parent khai `<inherited>false</inherited>` ngay dưới plugin, child không còn nhận plugin declaration qua inheritance thông thường. Nếu child vẫn muốn dùng Antrun, cần cấu hình theo cơ chế riêng hoặc quản lý version qua pluginManagement. Đây là biện pháp **rộng hơn** nhiều so với việc chặn một execution parent-only.

### 9.7. Hoàn nguyên POM và chạy kiểm chứng

Sau mỗi thí nghiệm, hoàn nguyên fragment đã đổi về POM gốc ở mục 8 rồi chạy:

~~~bash
mvn -B -ntp -f app/pom.xml validate
mvn -B -ntp -f app/pom.xml clean package
~~~

Đừng kết luận từ một file output cũ hoặc log của lần trước; với execution tạo mã/tài nguyên, cần xác nhận ảnh hưởng thực tế lên artifact sau khi build sạch.

## 10. Kế thừa nhiều tầng: grandparent, parent và child

Một tổ chức lớn thường có:

~~~text
company-parent (POM)
      |
      v
service-parent (POM)
      |
      v
payment-service (JAR)
~~~

Giả sử grandparent định nghĩa `security-check` ở `validate`, parent khai cùng `security-check` để bổ sung một số tham số, child lại khai cùng ID để thay target. Maven có thể ghép chúng qua **nhiều tầng parent chain**, tạo một execution logic có ID `security-check` với phase/goal/config cuối.

Nếu parent đặt `<inherited>false</inherited>` tại execution, nó có thể chặn việc truyền tác động đó xuống cấp sau. Nếu child khai `security-check-v2` thay vì `security-check`, nó có thể tạo thêm execution. Nếu một tầng dùng `combine.children="append"` hoặc `combine.self="override"`, thuộc tính XML cũng có thể được kế thừa và ảnh hưởng tới các tầng sau.

Vì vậy trước khi sửa hãy xác định:

- Parent nào thực sự được phân giải (đúng GAV và `relativePath`).
- POM nào chứa execution gốc.
- Các execution ở mỗi tầng có cùng ID hay khác.
- Tầng nào đặt `inherited=false`.
- Profile nào đang active, có bổ sung execution hay không.
- Những phần XML nào dùng `combine.*` và được ghép ở tầng nào.

**Không sửa một parent chung chỉ vì một child bị lỗi mà chưa xem ảnh hưởng tới những child khác.** Một execution ở parent có thể phục vụ nhiều module với mục đích khác nhau.

## 11. Profile có thể bổ sung execution nhưng bản thân profile không được kế thừa nguyên khối

Profile có thể bổ sung build plugin khi active:

~~~xml
<profiles>
    <profile>
        <id>ci-checks</id>
        <activation>
            <property>
                <name>ci.checks</name>
                <value>true</value>
            </property>
        </activation>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-antrun-plugin</artifactId>
                    <executions>
                        <execution>
                            <id>ci-banner</id>
                            <phase>validate</phase>
                            <goals><goal>run</goal></goals>
                            <configuration>
                                <target>
                                    <echo message="CI PROFILE ACTIVE"/>
                                </target>
                            </configuration>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
~~~

Đây là **fragment phân tích**, không phải POM hoàn chỉnh. Khi profile `ci-checks` active ở POM chứa nó, tác động của profile được áp dụng vào model. Nếu plugin/execution được kế thừa, child có thể nhận tác động đó; nhưng profile không tự được truyền nguyên khối như một đối tượng profile.

Nếu một execution được đưa vào từ profile trùng ID với execution trong POM/parent, nó có thể tham gia merge theo ID. Do đó hai môi trường dùng cùng file POM nhưng có profile active khác nhau có thể sinh effective executions khác nhau.

Kiểm tra:

~~~bash
mvn -B -ntp -f app/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:active-profiles
mvn -B -ntp -f app/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=app-effective-pom.xml
~~~

Nếu lệnh build thực tế có `-Pci-checks` hoặc `-Dci.checks=true`, phải tái hiện chúng ở lệnh điều tra. Không dùng effective POM không bật profile để kết luận về hành vi CI khi profile được bật.

## 12. Default executions và thứ tự thực thi

Một số execution IDs xuất hiện trong log/effective model là ID **mặc định của Maven lifecycle**, ví dụ:

~~~text
default-compile
default-testCompile
default-test
default-jar
default-cli
~~~

Chúng khác với ID `default` từ một execution trong POM không khai `<id>`. Khi Maven dùng `packaging=jar`, một số goals như `compiler:compile` đã được bind vào lifecycle. Vì thế thêm một execution mới của `compiler:compile` ở phase `compile` có thể khiến goal **chạy thêm lần nữa**.

Nếu bạn chỉ muốn đổi Java release, thường nên dùng:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

và đặt version Compiler Plugin phù hợp, thay vì tự khai một execution compiler thứ hai.

Trong cùng một phase:

- Packaging có thể cung cấp goals mặc định.
- Parent và child có thể cung cấp executions riêng.
- Một plugin có thể có nhiều executions cùng phase.
- Profiles có thể thêm executions khi active.

Maven thường chạy những goals từ packaging binding trước các goals bổ sung qua POM. Với executions khác ID, thứ tự parent trước child là nguyên tắc được tài liệu cấu hình plugin nêu. Tuy vậy **thứ tự cuối cùng** còn tùy lifecycle, plugin, execution order và Maven version; không nên dùng tên ID để “ra lệnh thứ tự” nếu plugin/phases không bảo đảm điều đó.

Nếu một task bắt buộc chạy sau task khác, hãy chọn phase và execution strategy phù hợp, rồi kiểm chứng bằng log/test thay vì mong thứ tự chữ cái của ID quyết định.

## 13. Các lỗi thường gặp và cách chẩn đoán

### 13.1. Goal chạy hai lần thay vì một lần

**Triệu chứng:** log có hai execution headers cho cùng goal, hoặc output file bị ghi hai lần.

**Nguyên nhân:** parent execution có ID `generate-code`, child tạo execution mới ID `generate-code-child`. Hai ID khác nhau nên cả hai có thể tồn tại.

**Sửa:** nếu muốn **sửa execution kế thừa**, dùng **cùng ID**. Nếu thật sự cần hai executions, giữ ID khác nhau nhưng bảo đảm outputs không xung đột.

### 13.2. Execution parent không thấy trong child

Kiểm tra:

1. Child có `<parent>` đúng GAV/relativePath?
2. Plugin ở `build/plugins` hay chỉ `pluginManagement`?
3. Plugin hoặc execution có `inherited=false`?
4. Profile chứa execution có active không?
5. Execution có phase/goals hợp lệ không?
6. Command Maven đã chạy tới phase đó chưa?
7. Có đang đọc log của **đúng module** không?

Không copy toàn bộ POM parent vào child như biện pháp đầu tiên; điều đó làm mất ý nghĩa quản lý tập trung.

### 13.3. Execution bị lọt xuống child dù chỉ dành cho parent

**Nguyên nhân:** thiếu `<inherited>false</inherited>` ở execution hoặc plugin.

**Sửa:** thêm inherited=false **đúng cấp**. Nếu còn các execution chia sẻ khác, chặn tại execution parent-only, không tại toàn plugin.

### 13.4. Thấy PARENT ONLY trong log root dù đã chặn inheritance

**Nguyên nhân:** root reactor thực thi **chính project parent**. Inherited=false không cấm execution ở parent.

**Sửa:** xem project headers; thử `mvn -f app/pom.xml validate` và effective POM child.

### 13.5. Child chỉnh XML nhưng vẫn giữ tham số parent

**Nguyên nhân:** default merge giữ các phần tử XML mà child chưa thay.

**Sửa:** dùng `combine.self="override"` trên phần tử muốn thay trọn hoặc khai đầy đủ trường cần ghi đè; sau đó kiểm tra effective POM.

### 13.6. Child thêm list nhưng list parent biến mất

**Nguyên nhân:** XML merge mặc định không phải nối vô điều kiện các phần tử lặp.

**Sửa:** xem `combine.children="append"` ở phần tử list, đồng thời kiểm tra plugin có hỗ trợ semantics đó hay không.

### 13.7. Child chuyển phase nhưng goal không chạy khi dự kiến

**Nguyên nhân:** execution cùng ID được ghi phase mới; hoặc execution chưa có goals, hoặc Maven chưa chạy tới phase tương ứng.

**Sửa:** xem effective execution `phase` và `goals`, đọc plugin descriptor để biết default phase nếu không khai, rồi chạy lệnh tới đúng phase.

### 13.8. Chỉ có pluginManagement mà không thấy goal chạy

**Nguyên nhân:** quản lý plugin không tự kích hoạt mọi goal.

**Sửa:** khai plugin trong `build/plugins` hoặc dùng một binding phù hợp. Với plugin do packaging mặc định bind, xem version/config hiệu lực thay vì giả định phải luôn khai lại.

### 13.9. Cùng một plugin được khai hai lần trong cùng POM

**Nguyên nhân:** người viết tạo hai `<plugin>` entries cùng groupId/artifactId để chia executions.

**Sửa:** gom vào **một plugin declaration** có nhiều `<execution>` IDs. Maven 3 thường cảnh báo duplicate plugin declarations và Maven 4 có validation chặt hơn.

### 13.10. Hai execution cùng plugin không có ID

**Nguyên nhân:** đều dùng ID mặc định `default`, dễ xảy ra trùng.

**Sửa:** dùng ID rõ nghĩa, duy nhất trong cùng plugin của cùng POM.

### 13.11. Build local khác CI

Xem Maven Wrapper, JDK, parent version, profiles, CLI `-D`/` -P `, `.mvn/maven.config` và plugin versions. Đặc biệt phải so **effective POM** sau merge, không chỉ so file child POM.

### 13.12. Thấy execution trong effective POM nhưng không thấy tác động

Effective POM thể hiện **model cấu hình**; nó không chứng minh goal đã được gọi, phase đã chạy hay plugin đã xử lý tham số như mong muốn. Cần xem goal log và output thực tế. Nếu goal skip do property/CLI hoặc lỗi điều kiện, execution vẫn có thể hiện diện trong model.

## 14. Quy trình điều tra có thể lặp lại

**Bước 1 — xác nhận môi trường và project:**

~~~bash
mvn -version
mvn -B -ntp -f app/pom.xml validate
~~~

Đảm bảo đúng Maven core, JVM và POM.

**Bước 2 — xác định plugin và execution đang gặp vấn đề:**

~~~text
plugin = org.apache.maven.plugins:maven-antrun-plugin:3.1.0
execution id = common-banner
phase = validate
goal = run
~~~

**Bước 3 — xuất effective POM và chú thích nguồn:**

~~~bash
mvn -B -ntp -f app/pom.xml org.apache.maven.plugins:maven-help-plugin:3.5.2:effective-pom -Dverbose=true -Doutput=app-effective-pom.xml
~~~

**Bước 4 — đọc đúng nhánh XML:** `project/build/plugins/plugin/executions/execution` của đúng plugin. Nếu có `pluginManagement`, đối chiếu riêng nhánh managed config.

**Bước 5 — lần theo parent và profile:** kiểm tra GAV/relativePath của parent, execution cùng/khác ID, `inherited`, `combine.*` và profile đang active.

**Bước 6 — đánh giá behavior:** chạy đúng phase và đọc output/log theo module. Nếu execution sinh file, kiểm tra artifact mới thực sự được tạo, không chỉ log báo BUILD SUCCESS.

**Bước 7 — thay đổi nhỏ:** chỉnh đúng ID/phase/configuration/inheritance thay vì copy toàn bộ POM.

**Bước 8 — xác minh lần cuối:** xuất lại effective POM, chạy `validate` hoặc `verify` và so kết quả. Với lab Java 17, chạy `clean package` và Java main để kiểm tra build không bị ảnh hưởng.

## 15. Bài tập thực hành kèm đáp án

**A — khác ID:** Parent có `prepare-A` ở `generate-sources`, child có `prepare-B` cùng phase/goal. Child có thể có cả hai không?

**Đáp án:** có, nếu các execution đều được áp dụng và mục tiêu phase/goal phù hợp. Vì khác ID, chúng không tự merge thành một.

**B — cùng ID:** Parent và child đều khai `prepare-A`, child chỉ sửa configuration. Có mặc định chạy hai lần không?

**Đáp án:** không. Maven ghép theo ID trong cùng plugin và ưu tiên cấu hình child tại phần tử tương ứng; xem effective POM để biết phần parent còn lại.

**C — inherited=false:** Parent có `root-only` với inherited=false. Khi `mvn validate` từ root thấy log `root-only`, có nghĩa child nhận nó không?

**Đáp án:** chưa. Đó có thể là execution của project parent; xem `-f app/pom.xml` và effective POM child.

**D — merge default:** Parent có `<options><strict>true</strict><lang>en</lang></options>`, child khai `<options><lang>vi</lang></options>`. `strict` còn không?

**Đáp án:** theo merge XML mặc định, `strict` có thể được giữ từ parent và `lang` lấy child. Muốn bỏ cả phần parent, dùng `combine.self="override"` tại `options`.

**E — nối list:** Child muốn giữ hai `<item>` của parent rồi thêm một item, nên dùng gì?

**Đáp án:** `combine.children="append"` ở phần tử list phù hợp; vẫn cần xác nhận plugin nhận danh sách đúng thứ tự.

**F — pluginManagement:** Parent quản lý Antrun execution trong `pluginManagement`, child không dùng Antrun qua build/plugins hoặc binding. Có chắc chạy `mvn validate` thì Antrun thực thi?

**Đáp án:** không. Quản lý không đồng nghĩa kích hoạt.

**G — parent/aggregator:** Root có `<modules>` nhưng child không có `<parent>`. Plugin executions có tự kế thừa không?

**Đáp án:** không. `<modules>` chỉ định reactor membership; `<parent>` mới tạo quan hệ inheritance.

**H — duplicate IDs:** Hai execution của một plugin trong cùng POM đều không có ID. Maven có tự đặt ID độc nhất không?

**Đáp án:** không nên giả định; ID mặc định là `default` nên có thể trùng và gây validation error. Đặt ID tường minh.

**I — default compile:** Project `jar` đã có binding `compiler:compile`, rồi thêm execution mới cùng goal ở phase `compile`. Có thể chạy compiler hai lần không?

**Đáp án:** có. Muốn đổi Compiler Plugin version/Java release, dùng quản lý plugin/configuration phù hợp thay vì thêm execution chỉ để thay tham số.

**J — thí nghiệm:** Với hai POM mẫu, chạy `mvn -f app/pom.xml validate`. Tìm những dòng nào?

**Đáp án:** `CHILD OVERRIDES COMMON`, `PARENT SHARED HOOK` và `CHILD EXTRA`. Không kỳ vọng `PARENT ONLY` trong log của child.

## 16. Checklist trước khi merge thay đổi parent POM

- [ ] Đã phân biệt parent inheritance và reactor aggregation.
- [ ] Đã xác định đúng plugin groupId/artifactId/version.
- [ ] Mỗi execution có ID có ý nghĩa và duy nhất trong cùng plugin của cùng POM.
- [ ] Child dùng cùng ID khi sửa execution parent, khác ID khi chủ ý thêm execution.
- [ ] Đã xem phase/goals/configuration sau merge, không chỉ đọc child POM.
- [ ] Đã phân biệt inherited=false ở plugin level và execution level.
- [ ] Không nhầm log root/parent với log của child module.
- [ ] Khi muốn thay toàn bộ XML element, đã xét `combine.self="override"`.
- [ ] Khi muốn nối list, đã xét `combine.children="append"` và semantics plugin.
- [ ] Đã phân biệt `build/plugins` với `build/pluginManagement`.
- [ ] Đã xét profile đang active và các tầng parent khác.
- [ ] Không thêm goal do packaging đã bind mặc định nếu không chủ ý chạy thêm.
- [ ] Đã xuất `help:effective-pom -Dverbose=true` của đúng module.
- [ ] Đã so execution ID trong log với effective POM và kiểm tra output thực.
- [ ] Đã thử trên Maven/JDK versions của CI và kiểm tra side effects.
- [ ] Nếu thay parent chung, đã đánh giá tác động tới tất cả modules kế thừa.

## 17. Tài liệu Apache Maven chính thức

1. [Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html): execution ID, merge theo hierarchy, thứ tự executions.
2. [POM Reference](https://maven.apache.org/pom.html): plugin/execution inheritance, `combine.children`, `combine.self`, pluginManagement.
3. [Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html): project inheritance, merge plugin executions, aggregation.
4. [Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html): phase, goal, default packaging bindings, execution order.
5. [Maven Model 3.9.9](https://maven.apache.org/ref/3.9.9/maven-model/maven.html): execution ID, phase, goals, inherited, configuration.
6. [Maven Help Plugin — help:effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): xuất model hiệu lực và chú thích nguồn.
7. [Maven Help Plugin — help:active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): kiểm tra profile active.
8. [Maven AntRun Plugin 3.1.0 — Usage](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/usage.html): goal `run` và Ant `target/echo`.
9. [Maven AntRun Plugin 3.1.0 — Target attributes](https://maven.apache.org/plugins-archives/maven-antrun-plugin-3.1.0/examples/tasksAttributes.html): cấu hình target Ant.
