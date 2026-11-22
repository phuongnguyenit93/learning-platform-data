# Quy tắc ghi đè và hợp nhất cấu hình giữa POM cha và POM con trong Maven

## 1. Vì sao phải hiểu cả “kế thừa”, “ghi đè” và “hợp nhất”?

Trong dự án Maven nhiều module, **parent POM** tập trung những quy tắc chung: phiên bản Java, phiên bản dependency, cấu hình plugin, repository và thông tin tổ chức. **Child POM** kế thừa những phần áp dụng được, rồi có thể khai báo giá trị riêng cho module của mình.

Kết quả cuối cùng không đơn giản là “toàn bộ POM cha cộng toàn bộ POM con”. Maven tạo một **effective POM** qua nhiều lớp:

~~~text
Super POM / mặc định của Maven
            |
            v
Parent POM (và các parent phía trên, nếu có)
            |
            v
Child POM + tác động của profiles đang active
            |
            v
Effective POM của child
            |
            v
Goals/plugins trong build lifecycle sử dụng cấu hình hiệu lực
~~~

Ở các phần tử có thể kế thừa, nhìn chung **cấu hình child có độ ưu tiên cao hơn khi xung đột cùng một trường**, còn những trường không bị thay thế vẫn có thể được giữ từ parent. Với danh sách dependency, plugin, execution hoặc cấu hình XML lồng nhau, Maven có **quy tắc ghép theo danh tính/ID hoặc tên phần tử**, vì vậy phải biết đang xét loại dữ liệu nào.

Bốn câu hỏi khi đọc POM:

1. **Trường này có được kế thừa không?**
2. **Child có khai báo lại cùng khóa hoặc phần tử không?**
3. **Khai báo của child sẽ thay thế hay hợp nhất với parent?**
4. **Effective POM và execution thực tế thể hiện kết quả nào?**

Đây là bài về **cơ chế inheritance/merge** của POM, khác với aggregation bằng **<modules>** hoặc dependency giữa hai JAR.

## 2. Maven xác định cha và con bằng cách nào?

Một child chỉ rõ parent thông qua **<parent>**:

~~~xml
<parent>
    <groupId>com.example</groupId>
    <artifactId>company-parent</artifactId>
    <version>1.0.0</version>
</parent>
<artifactId>billing-service</artifactId>
~~~

Maven dùng **groupId:artifactId:version của parent** để phân giải POM cha. Theo quy ước Maven 3, nó có thể xem **../pom.xml** hoặc **<relativePath>** được chỉ định, rồi sử dụng repository nếu cần; tọa độ parent thực tế phải khớp. **<relativePath/>** rỗng có thể được dùng khi muốn bỏ tìm kiếm parent theo filesystem mặc định của Maven 3.

Nếu parent có **groupId=com.example** và **version=1.0.0**, child không khai báo hai trường ấy sẽ nhận:

~~~text
Child groupId   = com.example
Child artifactId = billing-service
Child version   = 1.0.0
~~~

**artifactId của child không được kế thừa** từ parent; child phải có artifactId riêng. Child có thể ghi trực tiếp **<groupId>** hoặc **<version>** của chính nó để thay đổi hai giá trị tương ứng.

**Packaging cũng cần đọc riêng:** parent thông thường có **<packaging>pom</packaging>**, còn child không khai báo packaging sẽ dùng mặc định **jar**. Child không tự thừa hưởng **pom** từ parent. Nếu muốn child là parent/aggregator khác, cần khai báo **<packaging>pom</packaging>** phù hợp.

Sự tồn tại của **<modules>** trong parent giúp Maven reactor build các module, nhưng **không tự tạo quan hệ kế thừa**. Một module nằm trong danh sách modules nhưng không có **<parent>** trỏ tới POM ấy thì không nhận cấu hình parent thông qua quan hệ này.

## 3. Nhóm nào kế thừa, nhóm nào phải khai báo riêng?

Bảng dưới nêu quy tắc cho POM Maven 3 / model POM 4.0.0 thông thường:

| Thành phần | Quy tắc khi child kế thừa | Khi child khai báo lại |
| --- | --- | --- |
| **groupId**, **version** | Được kế thừa nếu child không ghi | Giá trị trực tiếp trong child là giá trị của child |
| **artifactId** | Không kế thừa | Child phải khai báo artifactId của mình |
| **packaging** | Không lấy packaging của parent; mặc định **jar** | Child chọn kiểu đóng gói riêng |
| **name** | Không kế thừa theo quy tắc POM thông thường | Child đặt tên hiển thị riêng |
| **properties** | Các key của parent có thể được kế thừa | Child cùng key thường thay giá trị parent |
| **dependencies** | Dependency khai báo trực tiếp ở parent có thể sang child | Dependency cùng danh tính được hợp nhất/ghi đè theo model; dependency khác được thêm |
| **dependencyManagement** | Các quy tắc quản lý dependency truyền xuống | Child có thể điều chỉnh managed entry cùng danh tính |
| **build/plugins** | Plugin và các execution/configuration có thể được kế thừa | Cùng plugin được hợp nhất, cùng execution ID được ghép; child ưu tiên khi xung đột |
| **build/pluginManagement** | Quản lý phiên bản/cấu hình plugin có thể truyền xuống | Child ghi đè hoặc bổ sung phần quản lý riêng |
| **build/resources**, **testResources**, reporting | Có quy tắc kế thừa/hợp nhất riêng | Cần xem cấu trúc và effective POM để biết chính xác |
| **repositories**, **pluginRepositories** | Có thể được kế thừa | Child có thể bổ sung/điều chỉnh entries theo khóa phù hợp |
| **profiles** | Định nghĩa profile không tự kế thừa như phần tử POM thông thường | Tác động của profile **đang active** ở parent có thể xuất hiện trong effective child |
| **modules** | Không tạo quan hệ parent/child | Phục vụ aggregation/reactor, không thay cho **<parent>** |

Một số metadata khác như **description, organization, licenses, developers, scm, url** cũng có thể kế thừa. Maven có xử lý đặc biệt đối với một số URL kế thừa, nên không phải mọi URL giữ nguyên tuyệt đối từng ký tự.

Bảng chỉ mô tả ý nghĩa chung. Khi một phần tử là danh sách hoặc có cấu hình XML nhiều cấp, hãy kiểm tra kết quả thực tế bằng **help:effective-pom**.

## 4. Ghi đè các giá trị đơn: child có cùng key thì thường thắng

Ví dụ parent:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <build.label>parent</build.label>
</properties>
~~~

Child:

~~~xml
<properties>
    <build.label>child</build.label>
</properties>
~~~

Trong effective POM của child, ba giá trị dự kiến là:

~~~properties
maven.compiler.release=17
project.build.sourceEncoding=UTF-8
build.label=child
~~~

Child **chỉ ghi đè build.label**, trong khi hai properties khác vẫn được kế thừa. Không cần copy toàn bộ **<properties>** từ parent vào child.

Trong các trường đơn mang ý nghĩa của model (chẳng hạn **<version>**, **<description>**), child cũng có thể đặt giá trị riêng. Với plugin goal configuration, một phần tử con có cùng tên thường ưu tiên giá trị child, nhưng toàn bộ cấu hình lồng nhau vẫn phải áp dụng quy tắc XML merge, không nên coi như thay thế toàn khối.

**Một property chỉ có tác dụng nếu có nơi sử dụng nó.** Tạo key **build.label** không tự làm JAR đổi tên hay chương trình in giá trị khác. Nếu plugin/POM không đọc property đó, nó chỉ là metadata cấu hình để tra cứu.

## 5. Dependency trong parent và child: thêm, hợp nhất, quản lý phiên bản

Có ba tình huống cần phân biệt.

### 5.1. Parent khai báo dependency trực tiếp trong dependencies

Ví dụ:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-lang3</artifactId>
        <version>3.16.0</version>
    </dependency>
</dependencies>
~~~

Nếu khai báo này nằm trực tiếp trong parent **<dependencies>**, child có thể kế thừa dependency đó ngay cả khi child không liệt kê lại. Điều này hữu ích cho dependency thực sự dùng ở **mọi** module, nhưng dễ làm các module nhận thư viện không cần thiết.

Nếu child khai báo lại dependency có cùng danh tính với thông tin khác, Maven sử dụng quy tắc merge/ưu tiên child cho trường xung đột. Đối với danh tính dependency trong model, cần xét các phần như **groupId, artifactId, type, classifier**, không chỉ nhìn version. Hai dependency khác danh tính không tự “thay nhau”; chúng có thể cùng tồn tại.

**Không nên khai báo trùng dependency hai lần trong cùng một POM** để thử tạo hiệu ứng ghi đè. Điều đó khác với quan hệ kế thừa hai POM và có thể tạo cảnh báo/lỗi model.

### 5.2. Parent chỉ quản lý dependency trong dependencyManagement

Ví dụ parent:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child muốn dùng JUnit thì tự khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

Child được áp dụng **version=5.11.4** và **scope=test** từ dependencyManagement kế thừa, theo điều kiện matching của Maven. **dependencyManagement không tự thêm JUnit vào dependencies** nếu child không sử dụng nó.

Đây là mẫu thực hành tốt cho nhiều module: parent kiểm soát version, mỗi child quyết định mình cần thư viện nào.

### 5.3. Child muốn version khác parent

Giả sử parent quản lý JUnit Jupiter **5.11.4**, nhưng child khai báo dependency trực tiếp với version riêng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.3</version>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong child, version trực tiếp **5.11.3** thắng giá trị managed **5.11.4** cho dependency ấy. Child cũng có thể định nghĩa **dependencyManagement** cùng key để điều chỉnh policy cho dependency không ghi version tại child.

Không nên tùy tiện đổi version chỉ để build xanh: nhiều dependency transitives cũng chịu ảnh hưởng từ dependency management, có thể gây xung đột runtime. Dùng **mvn dependency:tree** để nhìn kết quả dependency graph thực tế.

## 6. pluginManagement và plugins: nơi quản lý khác nơi kích hoạt

Parent thường đặt version chung:

~~~xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
~~~

Đây là cấu hình quản lý plugin. Một plugin được **quản lý** không có nghĩa mọi goal của nó tự chạy. Goal chỉ chạy khi plugin được gắn vào lifecycle hoặc được gọi trực tiếp; các plugin có **default lifecycle binding** theo packaging vẫn được áp dụng phần management tương ứng.

Nếu parent có **build/plugins** cho Surefire với cấu hình chung:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <reuseForks>true</reuseForks>
                <trimStackTrace>true</trimStackTrace>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Child có thể khai báo **cùng plugin**, ghi đè một giá trị:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <trimStackTrace>false</trimStackTrace>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Cấu hình hợp nhất có thể đọc trong effective POM của child:

~~~xml
<configuration>
    <reuseForks>true</reuseForks>
    <trimStackTrace>false</trimStackTrace>
</configuration>
~~~

Giá trị **trimStackTrace** từ child được ưu tiên; **reuseForks** giữ từ parent vì child không khai báo lại. Cách ghép này **không tự nhân đôi plugin Surefire**: trong model một plugin được nhận diện bằng **groupId:artifactId**.

**Chú ý:** nếu parent có plugin trong **pluginManagement** nhưng không có trong **build/plugins**, việc child khai báo plugin vào **build/plugins** là một cách làm cho cấu hình managed có tác dụng khi goal thực sự được gọi hoặc được bind vào lifecycle.

## 7. Quy tắc merge XML trong plugin configuration

Maven merge những phần tử bên trong **<configuration>** theo **tên element**, thay vì hiểu ngữ nghĩa kiểu danh sách Java mà plugin sẽ xử lý.

### 7.1. Default: merge; con ưu tiên trường cùng tên

Minh họa cấu hình của một plugin giả định, chỉ để giải thích model (không phải plugin chạy độc lập):

**Parent:**

~~~xml
<configuration>
    <options>
        <mode>safe</mode>
        <level>normal</level>
    </options>
</configuration>
~~~

**Child:**

~~~xml
<configuration>
    <options>
        <mode>fast</mode>
    </options>
</configuration>
~~~

Trong cấu hình hiệu lực, **mode=fast** từ child và **level=normal** từ parent:

~~~xml
<configuration>
    <options>
        <mode>fast</mode>
        <level>normal</level>
    </options>
</configuration>
~~~

Điều này khác với việc thay thế toàn bộ **<options>**. Nếu child chỉ đổi **mode**, nó có thể vô tình vẫn nhận **level** từ parent. Đó là quy tắc **merge** mặc định.

### 7.2. combine.children="append": ghép thêm các phần tử con

Giả sử parent có:

~~~xml
<configuration>
    <items>
        <item>parent-a</item>
        <item>parent-b</item>
    </items>
</configuration>
~~~

Child muốn bổ sung, giữ nguyên thứ tự parent trước child:

~~~xml
<configuration>
    <items combine.children="append">
        <item>child-c</item>
    </items>
</configuration>
~~~

Kết quả:

~~~xml
<configuration>
    <items combine.children="append">
        <item>parent-a</item>
        <item>parent-b</item>
        <item>child-c</item>
    </items>
</configuration>
~~~

**combine.children="append"** rất có ích khi một plugin mong đợi danh sách XML gồm nhiều phần tử cùng tên. Không nên nghĩ default merge luôn nối mọi danh sách; nếu cần nối, hãy đánh dấu có chủ đích và đọc effective POM.

### 7.3. combine.self="override": thay toàn bộ khối tại vị trí đó

Parent:

~~~xml
<configuration>
    <options>
        <mode>safe</mode>
        <level>normal</level>
    </options>
</configuration>
~~~

Child muốn loại bỏ tất cả phần tử options từ parent:

~~~xml
<configuration>
    <options combine.self="override">
        <mode>fast</mode>
    </options>
</configuration>
~~~

Kết quả phần options chỉ còn:

~~~xml
<options combine.self="override">
    <mode>fast</mode>
</options>
~~~

**level=normal** không còn được thừa hưởng trong khối này. Khi một phần cấu hình của parent không được phép áp dụng cho child, **combine.self="override"** làm ý định rõ ràng hơn so với việc chỉ bỏ bớt các XML nodes.

### 7.4. Giới hạn và độ ưu tiên của các thuộc tính combine.*

- **combine.children="merge"** và **combine.self="merge"** là hành vi mặc định tương ứng.
- **combine.children="append"** nối phần tử con của parent trước rồi tới phần tử con child tại node mang thuộc tính.
- **combine.self="override"** thay cả nội dung node của parent bằng node ở child.
- Nếu cùng một node dùng **combine.self="override"** và **combine.children="append"**, override được ưu tiên; không nên cấu hình hai ý nghĩa xung đột.
- Các thuộc tính này áp dụng **tại node được khai báo**, không có nghĩa mọi node lồng sâu đều tự chuyển sang append/override.
- Một số thuộc tính combine có thể được kế thừa sang thế hệ POM tiếp theo, nên thay đổi ở parent có thể ảnh hưởng tới grandchildren.
- Chúng phục vụ **plugin configuration XML**, không phải cú pháp tổng quát để nối mọi danh sách **dependencies**, **modules**, hay **repositories** trong POM.

Chỉ nên dùng chúng khi hiểu chính xác cấu hình mà plugin đích cần. **Effective POM** giúp kiểm tra XML đã merge, nhưng để xác nhận plugin thực sự hiểu nội dung đúng ý, vẫn cần chạy goal và xem kết quả thực tế.

## 8. Plugin executions: trùng ID được hợp nhất, ID khác là execution khác

Một plugin có thể có nhiều **<execution>**. Đối với cùng plugin, **execution ID** là khóa quan trọng khi Maven hợp nhất cấu hình từ cha và con.

**Parent:**

~~~xml
<executions>
    <execution>
        <id>check-quality</id>
        <phase>verify</phase>
        <goals>
            <goal>check</goal>
        </goals>
        <configuration>
            <failOnError>true</failOnError>
        </configuration>
    </execution>
</executions>
~~~

**Child:**

~~~xml
<executions>
    <execution>
        <id>check-quality</id>
        <configuration>
            <failOnError>false</failOnError>
        </configuration>
    </execution>
</executions>
~~~

Đây là **mảnh XML minh họa**; để chạy thực tế phải đặt nó dưới plugin cung cấp goal **check**, và có đủ cấu hình bắt buộc. Vì hai execution có cùng **id=check-quality**, Maven **merge theo ID**; phần trùng được child ưu tiên, phần không được child thay thế (chẳng hạn phase và goal được kế thừa trong ví dụ) có thể được giữ lại. Đây **không phải hai lượt execution độc lập** cùng ID.

Nếu child khai báo một execution với ID mới, chẳng hạn **check-quality-child**, nó tạo thêm execution riêng. Khi nhiều goals được bind vào cùng phase, kết quả và thứ tự cần được kiểm tra trong log/effective POM theo cấu hình thực tế.

Để tránh nhầm:

- **Cùng plugin + cùng execution id**: Maven ghép model execution, child có thể thay nội dung xung đột.
- **Cùng plugin + khác execution id**: cả hai execution có thể xuất hiện trong model hiệu lực.
- **Hai plugin khác nhau**: execution ID trùng chữ không làm chúng trở thành một plugin.
- **Hai execution có cùng ID trong một POM đơn lẻ** là khai báo không hợp lệ hoặc ít nhất làm model không đúng kỳ vọng; đừng dùng làm kỹ thuật ghi đè.

Các trường **<phase>**, **<goals>**, **<configuration>** trong execution có vai trò khác nhau; không nên suy ra “ghi đè cùng ID” sẽ xóa toàn bộ mọi phần tử parent. Hãy kiểm tra nội dung sau merge trước khi dựa vào nó.

## 9. Ngăn một plugin/execution kế thừa với inherited=false

Đôi khi một plugin chỉ nên chạy tại parent, ví dụ tạo báo cáo tổng hợp ở project aggregator.

Trong **parent POM**, có thể dùng:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-antrun-plugin</artifactId>
    <version>3.1.0</version>
    <inherited>false</inherited>
    <executions>
        <execution>
            <id>parent-only-task</id>
            <phase>validate</phase>
            <goals><goal>run</goal></goals>
            <configuration>
                <target><echo message="parent-only"/></target>
            </configuration>
        </execution>
    </executions>
</plugin>
~~~

**<inherited>false</inherited>** ở plugin nói rằng cấu hình plugin này **không tự truyền xuống child**. Plugin vẫn có thể chạy ở parent khi phase được gọi; cờ này không có nghĩa “bỏ chạy plugin tại parent”.

Nếu muốn ngăn **một execution cụ thể** nhưng cho phép các execution khác của cùng plugin được kế thừa, đặt **<inherited>false</inherited>** ngay trong execution cần chặn:

~~~xml
<execution>
    <id>parent-only-task</id>
    <phase>validate</phase>
    <goals><goal>run</goal></goals>
    <inherited>false</inherited>
    <configuration>
        <target><echo message="parent-only"/></target>
    </configuration>
</execution>
~~~

Hai đoạn là các phương án minh họa ở **hai cấp khác nhau**, không cần dùng đồng thời. Nếu child thực sự cần plugin riêng, child vẫn có thể khai báo cấu hình plugin của chính nó.

**inherited=false** không phải cách biến một dependency bị kế thừa thành “scope=provided”, cũng không phải cách chặn inheritance của toàn bộ parent POM. Phạm vi tác động là plugin hoặc execution nơi cờ được khai báo.

## 10. Ví dụ đầy đủ với Maven 3.9+ và Java 17

Ví dụ sau tạo một parent POM và một module con thực sự. Nó minh họa đồng thời:

- Child kế thừa **groupId/version** và **maven.compiler.release=17**.
- Child ghi đè property **build.label**.
- Child nhận **version/scope của JUnit** từ parent **dependencyManagement**.
- Parent quản lý phiên bản Compiler, Surefire, JAR plugins.
- Parent có cấu hình Surefire chung, child thay **trimStackTrace** nhưng giữ **reuseForks**.

### 10.1. Cấu trúc dự án

~~~text
maven-merge-demo/
├── pom.xml
└── demo-app/
    ├── pom.xml
    └── src/
        ├── main/
        │   └── java/com/example/demo/App.java
        └── test/
            └── java/com/example/demo/AppTest.java
~~~

Không cần tự tạo **target/**; Maven sinh thư mục này khi build.

### 10.2. Parent POM: maven-merge-demo/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>merge-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>demo-app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <build.label>parent</build.label>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit.jupiter</groupId>
                <artifactId>junit-jupiter</artifactId>
                <version>5.11.4</version>
                <scope>test</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.13.0</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-jar-plugin</artifactId>
                    <version>3.4.2</version>
                </plugin>
            </plugins>
        </pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <reuseForks>true</reuseForks>
                    <trimStackTrace>true</trimStackTrace>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Parent đóng gói kiểu **pom** để làm aggregator/parent. Mục **modules** dùng để build **demo-app** trong cùng reactor; chính **<parent>** trong POM con mới xác định quan hệ kế thừa.

### 10.3. Child POM: maven-merge-demo/demo-app/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>merge-parent</artifactId>
        <version>1.0.0</version>
    </parent>
    <artifactId>demo-app</artifactId>

    <properties>
        <build.label>child</build.label>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <configuration>
                    <trimStackTrace>false</trimStackTrace>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Child không khai báo **groupId**, **version**, **packaging** hay JUnit version/scope. Maven xác định:

| Thuộc tính hiệu lực | Giá trị | Nguồn |
| --- | --- | --- |
| **groupId** | **com.example** | Parent |
| **artifactId** | **demo-app** | Child |
| **version** | **1.0.0** | Parent |
| **packaging** | **jar** | Mặc định khi child không ghi |
| **maven.compiler.release** | **17** | Parent property |
| **build.label** | **child** | Child ghi đè |
| **JUnit Jupiter version** | **5.11.4** | Parent dependencyManagement |
| **JUnit Jupiter scope** | **test** | Parent dependencyManagement |
| **Surefire reuseForks** | **true** | Parent plugin configuration |
| **Surefire trimStackTrace** | **false** | Child plugin configuration |

### 10.4. Java 17 class trong module con

Tạo **demo-app/src/main/java/com/example/demo/App.java**:

~~~java
package com.example.demo;

public final class App {
    private App() {
    }

    public static String message() {
        return "POM merge works";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
~~~

Tạo **demo-app/src/test/java/com/example/demo/AppTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void inheritedJunitSettingsWork() {
        assertEquals("POM merge works", App.message());
    }
}
~~~

Test dùng JUnit Jupiter do child khai báo dependency và được parent quản lý version/scope. Main class không cần JUnit ở runtime.

### 10.5. Biên dịch, chạy test và xem artifact

Yêu cầu: JDK 17+ và Maven 3.9+ có khả năng phân giải plugin/dependency. Chạy tại thư mục **maven-merge-demo/**:

~~~bash
mvn -version
mvn clean verify
java -cp demo-app/target/classes com.example.demo.App
jar tf demo-app/target/demo-app-1.0.0.jar
~~~

Khi build thành công, Surefire chạy **1 test**, **0 failures/0 errors**; dòng log cụ thể có thể khác theo cấu hình. Lệnh Java in stdout chính xác:

~~~text
POM merge works
~~~

JAR chính mặc định có **com/example/demo/App.class** và không tự đưa **AppTest.class** vào. POM chưa cấu hình **Main-Class** trong manifest, vì vậy dùng **java -cp** thay vì mặc định cho rằng **java -jar** chạy được.

### 10.6. Kiểm tra config được ghép bằng Help Plugin

Từ thư mục **demo-app/**, chạy:

~~~bash
mvn help:effective-pom -Doutput=effective-pom.xml
mvn help:evaluate -Dexpression=project.groupId -q -DforceStdout
mvn help:evaluate -Dexpression=project.artifactId -q -DforceStdout
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
mvn help:evaluate -Dexpression=project.packaging -q -DforceStdout
mvn help:evaluate -Dexpression=build.label -q -DforceStdout
~~~

Giá trị kỳ vọng theo đúng thứ tự của **năm lệnh help:evaluate**:

~~~text
com.example
demo-app
1.0.0
jar
child
~~~

Trong **effective-pom.xml**, tìm phần **maven-surefire-plugin** và xác nhận có **reuseForks=true**, **trimStackTrace=false**, cùng version/plugin configuration phù hợp. Tìm dependency **junit-jupiter** trong **dependencies** để xác nhận version/scope đã được áp dụng.

File **effective-pom.xml** là đầu ra chẩn đoán, không phải nơi để chỉnh sửa cấu hình gốc. Không nên commit file này nếu repository không có yêu cầu riêng.

## 11. Sự ưu tiên giữa parent, child, BOM và dependency trực tiếp

Không chỉ có một “thứ tự ưu tiên XML” áp dụng cho mọi tình huống:

- **Kế thừa POM:** với trường đơn có thể kế thừa, khai báo child thường ưu tiên khi trùng field.
- **dependencyManagement:** mục managed dependency áp dụng khi dependency phù hợp cần giá trị được quản lý; version khai báo trực tiếp ở dependency thường ưu tiên giá trị managed.
- **Management trong child:** child có thể quản lý version khác parent cho dependency cùng danh tính; điều này ảnh hưởng phạm vi quản lý dependency của child.
- **BOM import:** khai báo **scope=import**, **type=pom** trong dependencyManagement cho phép nhập các managed dependencies từ BOM, nhưng **không kế thừa toàn bộ pluginManagement/properties/modules của BOM** như một parent POM.
- **pluginManagement:** quản lý phiên bản/cấu hình, tác động đến plugin được sử dụng; không tự tạo lifecycle execution cho plugin tùy ý.
- **plugin executions:** ghép theo plugin identity và execution ID; child có thể thay fields xung đột, còn execution ID mới tạo thêm cấu hình.
- **plugin configuration:** XML merge theo tên phần tử; dùng **combine.children** hoặc **combine.self** khi cần thay đổi cách hợp nhất.

**BOM không thay thế parent:** mỗi POM con có một parent trực tiếp, nhưng có thể nhập BOM cho phần quản lý dependency. Khi nhiều nguồn cùng quản lý một dependency, hãy quan sát effective POM và dependency tree thay vì suy luận đơn giản từ thứ tự xuất hiện trong tài liệu.

## 12. Profiles và thuộc tính môi trường có thể làm kết quả khác đi

Một parent POM có thể khai báo profile để bật rule, plugin hoặc properties khi JDK/OS/property đáp ứng điều kiện.

**Định nghĩa profile không được child kế thừa như một phần tử POM thông thường**, nhưng tác động của profile **đang active tại parent** có thể được nhập vào phần model mà child nhận. Nếu profile khác nhau giữa laptop và CI, effective POM hoặc output build cũng có thể khác nhau.

Kiểm tra:

~~~bash
mvn help:active-profiles
mvn help:effective-pom -Dverbose
~~~

Tham số **-Dverbose** trên Help Plugin có thể cung cấp chú thích về nguồn của một số cấu hình. Nó hỗ trợ lần ngược từ giá trị hiệu lực về khai báo cha/con, tùy phiên bản Help Plugin.

User properties **-D...** hoặc **settings.xml** cũng có thể ảnh hưởng việc giải quyết version/repository và thực thi plugin. Vì vậy, khi tranh luận “child đã ghi đè parent chưa”, cần kiểm tra cùng môi trường, active profiles và lệnh chạy cụ thể.

## 13. Cách giải quyết xung đột mà không làm POM khó bảo trì

Một số nguyên tắc khi thiết kế parent/child:

1. **Đặt shared compiler/JDK, encoding và plugin versions ở parent.** Các module có mặc định thống nhất.
2. **Đặt dependency versions chung trong dependencyManagement.** Child tự khai báo dependency cần dùng.
3. **Chỉ ghi đè trường cần khác ở child.** Đừng copy toàn bộ cấu hình parent chỉ để đổi một cờ.
4. **Dùng pluginManagement để quản lý; build/plugins để chọn và cấu hình plugin thực sự sử dụng.** Hiểu default lifecycle bindings theo packaging.
5. **Sử dụng execution IDs có ý nghĩa và ổn định.** Nếu child muốn tùy chỉnh một execution từ parent, dùng cùng ID; nếu muốn thêm việc độc lập, dùng ID khác.
6. **Dùng inherited=false ở parent khi một execution không nên truyền xuống child.** Không dựa vào việc child biết và tự tắt từng task không thuộc trách nhiệm của nó.
7. **Dùng combine.children=append khi thực sự cần nối danh sách XML; combine.self=override khi cần thay toàn khối.** Kiểm tra plugin có chấp nhận cấu trúc sau merge.
8. **Tránh khai báo cùng dependency hoặc cùng plugin hai lần trong cùng một POM.** Sự hợp nhất giữa parent/child không hợp thức hóa duplicate declarations ở cùng tầng.
9. **Dùng effective POM để kiểm tra kết quả model, và chạy goal/test để kiểm tra hành vi.** Effective POM không tự chứng minh một goal đã chạy.
10. **Tách inheritance khỏi aggregation.** Parent có thể quản lý cấu hình cho module ở repository khác; aggregator có thể build module không kế thừa nó.

Trong tổ chức có nhiều lớp parent, một giá trị child nhìn thấy có thể tới từ **grandparent**, parent trực tiếp hoặc Super POM. Hãy truy theo chuỗi kế thừa để biết nơi đặt cấu hình bền vững nhất.

## 14. Các lỗi thường gặp và cách chẩn đoán

| Dấu hiệu | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Child compile bằng Java release không mong muốn | Child/property/profile đã ghi đè release từ parent; compiler plugin dùng cấu hình khác | Xem **maven.compiler.release**, compiler config và effective POM |
| JUnit version không khớp với parent management | Child khai báo trực tiếp version khác, child management/BOM thay policy | Xem **dependencies**, **dependencyManagement**, dependency tree |
| Plugin vẫn còn cấu hình parent dù child đã khai báo plugin | Default XML merge giữ lại các node mà child không thay | Xem cấu hình node và dùng override có chủ đích |
| Một danh sách XML bị mất giá trị parent | Default merge theo tên element, không nối list | Cân nhắc **combine.children="append"** tại node danh sách phù hợp |
| Muốn bỏ toàn bộ phần tử cha mà vẫn nhận child + parent | Chưa dùng **combine.self="override"** ở đúng node | Đặt override tại phần tử cần thay và xem effective POM |
| Goal không chạy dù pluginManagement có cấu hình | Chưa có plugin/lifecycle binding/execution thực sự | Xem **build/plugins**, packaging và execution plan |
| Một goal chạy ở child dù tưởng chỉ thuộc parent | Plugin/execution được kế thừa theo mặc định | Thêm **inherited=false** ở đúng cấp trong parent |
| Một execution bị thay khi child dùng cùng ID | Execution cùng ID được ghép theo model | Đổi ID nếu muốn execution bổ sung; giữ ID nếu cần tùy chỉnh |
| Build có hai behavior khác nhau local/CI | Profiles, -D properties, settings, JDK/Maven khác | So sánh active profiles, effective POM và log plugin |
| Child không phân giải được parent | Sai tọa độ parent, relativePath, cache hoặc repo | Kiểm tra **<parent>**, nơi lưu POM, kết nối repository |
| Có <modules> nhưng không kế thừa | Aggregation không tự tạo inheritance | Kiểm tra **<parent>** ngay trong POM module |
| Effective POM đúng nhưng plugin hành xử khác | Plugin interpret config riêng; goal/plugin version khác hoặc skip | Kiểm tra log plugin, version, parameters và build outputs |

Một bước chẩn đoán hữu ích là giảm bài toán xuống **một trường**: ví dụ **trimStackTrace**, **maven.compiler.release** hoặc version của một dependency. Xác định giá trị ở parent, ở child, trong effective POM, rồi mới xem kết quả chạy. Không nên sửa hàng loạt XML cùng lúc khiến mất dấu phần nào thật sự tác động.

## 15. Bài tập tự kiểm tra

Giả sử parent cung cấp:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <service.region>global</service.region>
</properties>
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child:

~~~xml
<properties>
    <service.region>apac</service.region>
</properties>
<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
    </dependency>
</dependencies>
~~~

**Câu 1:** Child nhận compiler release nào? **17**, do parent property được kế thừa.

**Câu 2:** Giá trị service.region trong child là gì? **apac**, do child ghi đè cùng property key.

**Câu 3:** Child có JUnit dependency không? **Có**, vì child khai báo trong **dependencies**; parent chỉ cung cấp version/scope.

**Câu 4:** Version/scope của JUnit trong child? **5.11.4/test**, theo dependencyManagement kế thừa.

**Câu 5:** Nếu parent có plugin configuration với hai node **mode** và **level**, child chỉ đổi **mode**, **level** còn không? **Thông thường có** theo XML merge mặc định. Dùng **combine.self="override"** khi muốn thay toàn bộ node cha.

**Câu 6:** Nếu parent và child đều có execution ID **check-quality** trong cùng plugin, Maven có coi là hai execution độc lập không? **Không theo model inheritance:** chúng được hợp nhất theo ID; cần xem effective POM để xác định goal/phase/config cuối cùng.

## 16. Checklist kiểm tra POM kế thừa trong dự án thật

1. Mở child **pom.xml**, xác định **<parent>** và **relativePath**.
2. Xác nhận parent đúng artifact và có thể phân giải; xem cả grandparent nếu có.
3. Xác định các trường không kế thừa như **artifactId**, **name**, và packaging mặc định của child.
4. So sánh **properties**; ghi nhận key trùng được child thay.
5. So sánh **dependencies** với **dependencyManagement**; phân biệt khai báo dùng thư viện với chỉ quản lý version.
6. So sánh **build/plugins** với **pluginManagement** và các execution IDs.
7. Với plugin configuration lồng nhau, tìm **combine.children**, **combine.self**, **inherited=false**.
8. Kiểm tra **profiles** đang active; đừng chỉ đọc các profile được định nghĩa trong parent.
9. Chạy **mvn help:effective-pom -Dverbose**, **mvn help:evaluate** và **mvn dependency:tree** khi cần.
10. Chạy goal/lifecycle liên quan, kiểm tra log và output artifact trước khi kết luận cấu hình đã hoạt động đúng.

Tư duy hữu ích nhất là tách thành ba tầng: **khai báo ở parent**, **ngoại lệ ở child**, và **giá trị hiệu lực mà Maven đã merge**. Khi ba tầng được quan sát riêng, bạn có thể giảm lặp POM, dùng chung chính sách build và cho phép mỗi module tùy chỉnh có kiểm soát.

## Tài liệu tham khảo

- [Apache Maven — POM Reference: Inheritance và plugin configuration](https://maven.apache.org/pom.html)
- [Apache Maven — Introduction to the POM](https://maven.apache.org/guides/introduction/introduction-to-the-pom.html)
- [Apache Maven — Guide to Configuring Plug-ins](https://maven.apache.org/guides/mini/guide-configuring-plugins.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven Help Plugin — effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
