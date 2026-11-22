# Maven optional dependency và ảnh hưởng đến dự án tiêu thụ thư viện

## 1. Vấn đề cần giải quyết: thư viện dùng một tính năng nhưng ứng dụng không dùng

Maven quản lý thư viện thông qua phần `<dependencies>` trong **pom.xml**. Bình thường, khi ứng dụng phụ thuộc vào một thư viện, Maven có thể kéo theo cả những thư viện mà thư viện đó cần: đây là **transitive dependencies** (phụ thuộc bắc cầu). Điều này thuận tiện nhưng không phải mọi dependency của thư viện đều cần thiết cho mọi ứng dụng tiêu thụ.

Giả sử thư viện **feature-lib** cung cấp hai chức năng:

- Chức năng cơ bản: tạo lời chào; chỉ cần Java chuẩn.
- Chức năng mở rộng: trang trí lời chào nhờ một thư viện riêng là **optional-helper**.

Ứng dụng **consumer-app** chỉ gọi chức năng cơ bản thì không nhất thiết phải tải optional-helper vào dependency graph của chính nó. Maven cho phép tác giả feature-lib đánh dấu quan hệ đến optional-helper là:

~~~xml
<optional>true</optional>
~~~

**Ý nghĩa chính xác:** feature-lib **vẫn có dependency trực tiếp** vào optional-helper cho các classpath thích hợp của chính feature-lib; nhưng một project **khác** chỉ phụ thuộc vào feature-lib **không tự nhận optional-helper qua nhánh bắc cầu đó**. Nếu project tiêu thụ muốn dùng tính năng mở rộng, project ấy phải chủ động khai báo dependency cần thiết.

Tài liệu chính thức của Apache Maven mô tả optional dependencies như những phụ thuộc được **loại trừ khỏi đường truyền bắc cầu theo mặc định** đối với project tiêu thụ, không phải một cơ chế tự tải dependency khi chức năng được gọi lúc runtime.

## 2. Mô hình A → B → C và nơi optional thực sự phát huy tác dụng

Đặt tên:

- **A:** consumer-app, ứng dụng dùng thư viện.
- **B:** feature-lib, thư viện do nhóm phát triển.
- **C:** optional-helper, thư viện chỉ cần cho tính năng mở rộng của B.

Không có optional:

~~~text
A (consumer-app)
  |
  +-- B (feature-lib)
        |
        +-- C (optional-helper, compile)
        
Classpath phụ thuộc thông thường của A có thể nhận B và C.
~~~

Khi B khai báo C là optional:

~~~text
A (consumer-app)
  |
  +-- B (feature-lib)
        |
        +-- C (optional-helper, compile, optional=true)
              ^
              |
              B dùng C khi biên dịch/chạy tính năng mở rộng.
              A không tự nhận C qua nhánh B -> C.
~~~

**Hai góc nhìn khác nhau:**

| Góc nhìn | Có C không? | Vì sao |
| --- | --- | --- |
| Build **B** | Có, theo scope của B→C | B đã trực tiếp khai báo dependency vào C |
| Build **A** khi A chỉ phụ thuộc B | Không qua nhánh B→C | B→C là optional, nên transitivity bị ngắt tại nhánh đó |
| Build **A** khi A trực tiếp khai báo C | Có | A tự quyết định dùng C |
| Build **A** khi một thư viện D khác mang C vào theo nhánh không optional | Có thể có | Optional ở B→C không xóa C khỏi toàn bộ dependency graph |
| Runtime của A khi C không có mặt | Tính năng không cần C có thể hoạt động; đường code cần C có thể lỗi | Optional không cài đặt một cơ chế fallback tự động |

**Điểm then chốt:** optional là một thuộc tính của **khai báo dependency trong POM của project đang phụ thuộc**, không phải “thuộc tính toàn cục của artifact C”. Artifact C không trở nên optional với mọi project chỉ vì B đánh dấu nó optional.

## 3. Cú pháp trong pom.xml và giá trị mặc định

Ví dụ trong POM của **feature-lib**:

~~~xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>optional-helper</artifactId>
        <version>1.0.0</version>
        <scope>compile</scope>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Giải thích:

- `groupId`, `artifactId`, `version` định danh artifact cần dùng.
- `scope=compile` cho biết dependency có mặt ở classpath compile và những classpath thích hợp của **feature-lib**. Đây là scope mặc định nếu không khai báo.
- `optional=true` làm Maven không tự truyền dependency qua **quan hệ bắc cầu tới các project tiêu thụ feature-lib**.
- Nếu không có thẻ optional hoặc khai báo `<optional>false</optional>`, quy tắc bắc cầu thông thường áp dụng theo scope/exclusions/dependency mediation.

**Không viết `optional` để thay `scope`.** Scope quyết định *dependency tham gia classpath nào* và ảnh hưởng tính bắc cầu; optional quyết định *có truyền tiếp cho project tiêu thụ qua quan hệ này không*. Hai cơ chế có thể cùng xuất hiện trên một khai báo dependency.

**Không đặt optional trên project A rồi kỳ vọng B đổi cách build.** Thuộc tính ấy luôn gắn với dependency mà **POM chứa nó** khai báo.

## 4. Điều optional không làm

Đây là những hiểu lầm phổ biến nhất:

1. **Không làm C biến mất khỏi classpath của B.** B vẫn phụ thuộc trực tiếp vào C, nên mã B dùng C có thể biên dịch và chạy trong môi trường phù hợp.
2. **Không tự phát hiện feature được dùng rồi tải C lúc runtime.** Maven giải quyết dependency lúc build; Java class loading không tự hỏi Maven tải JAR khi thiếu class.
3. **Không khiến C trở thành thư viện test-only.** B cần C ở production thì scope vẫn có thể là compile/runtime.
4. **Không bảo đảm A tuyệt đối không có C.** A có thể khai báo C trực tiếp hoặc nhận nó từ D theo nhánh khác.
5. **Không giải quyết việc mã B cần C để khởi tạo mọi class.** Nếu đường chạy phổ biến bắt buộc tham chiếu C, optional có thể làm ứng dụng tiêu thụ lỗi.
6. **Không thay cho cơ chế module/adapter architecture.** Nếu có thể tách tính năng mở rộng ra module riêng, đó thường là cấu trúc rõ ràng hơn.
7. **Không phải giới hạn bảo mật/sandbox.** Nó không ngăn một build plugin hoặc dependency khác tải C, và không tự ngăn người dùng đưa C vào application classpath.
8. **Không phải BOM import hoặc dependencyManagement.** Chỉ quản lý version không tương đương khai báo dependency optional; xem phần so sánh.

## 5. Trách nhiệm của tác giả thư viện B

Nếu viết một thư viện mà nhiều ứng dụng khác sẽ dùng, tác giả nên đặt câu hỏi:

- C có bắt buộc với **mọi** chức năng cốt lõi của B không?
- C có được dùng trong chữ ký public API mà hầu hết người dùng phải biên dịch không?
- Nếu C vắng mặt, phần chức năng không cần C có thể được tải và chạy an toàn không?
- Tài liệu cho người tiêu thụ có ghi rõ feature nào cần thêm C, phiên bản nào tương thích, và ví dụ dependency trực tiếp chưa?
- Có thể thay optional bằng một **module riêng** như `feature-lib-core` và `feature-lib-adapter` không?

Nếu phần lớn chức năng của B đều cần C, **đừng đánh optional chỉ để giảm dependency tree**. Điều đó có thể làm tăng lỗi runtime cho người tiêu thụ. Nếu C chỉ phục vụ một adapter hoặc provider hiếm khi được chọn, optional thường hợp lý.

**Giữ API cốt lõi không phụ thuộc kiểu của C:** nếu method public của B nhận hoặc trả về class từ C, người tiêu thụ có thể cần C **ngay khi biên dịch hoặc phản chiếu chữ ký**, dù họ định sử dụng một phần khác của B. Nên cô lập implementation cần C ở class/adapter thích hợp, hoặc cung cấp module adapter tách riêng.

## 6. Ví dụ đầy đủ ba module, dùng Maven 3.9+ và Java 17

Ví dụ sau không phụ thuộc thư viện bên ngoài để chứng minh hành vi optional. Tất cả source là Java 17, có thể tạo trong một workspace mới và chạy bằng Maven.

Ba module:

1. **optional-helper:** cung cấp công cụ trang trí chuỗi.
2. **feature-lib:** có chức năng basic không cần helper, và chức năng extra cần helper. **feature-lib** khai báo helper là optional.
3. **consumer-app:** chỉ khai báo dependency vào feature-lib. Sau đó thử khai báo thêm helper để dùng extra.

### 6.1. Cấu trúc thư mục

~~~text
optional-dependency-demo/
├── pom.xml
├── optional-helper/
│   ├── pom.xml
│   └── src/main/java/dev/example/helper/FeatureHelper.java
├── feature-lib/
│   ├── pom.xml
│   └── src/main/java/dev/example/library/FeatureLibrary.java
└── consumer-app/
    ├── pom.xml
    └── src/main/java/dev/example/consumer/ConsumerApp.java
~~~

Các đường dẫn **src/main/java** tuân theo quy ước Java/Maven. Có thể tạo thư mục bằng IDE hoặc hệ điều hành; không cần tự tạo target.

### 6.2. Parent POM: optional-dependency-demo/pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.example</groupId>
    <artifactId>optional-dependency-demo</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <modules>
        <module>optional-helper</module>
        <module>feature-lib</module>
        <module>consumer-app</module>
    </modules>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

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
    </build>
</project>
~~~

Đây là **aggregator** và đồng thời là **parent** cho các module. Nó khai báo Java release 17 và pin các phiên bản plugin lifecycle chuẩn. Phần `<modules>` quyết định các module tham gia reactor; quan hệ parent thực sự sẽ được khai báo trong POM của từng module.

### 6.3. POM của optional-helper

Tạo **optional-helper/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>optional-dependency-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>optional-helper</artifactId>
</project>
~~~

**Lưu ý kỹ thuật:** một POM thông thường sử dụng `xsi:schemaLocation` theo cặp namespace và XSD. Để tránh sai khi tự nhập, có thể dùng dòng schemaLocation chuẩn như ở parent POM:

~~~xml
xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd"
~~~

Trong ví dụ này hãy **sử dụng dòng schemaLocation chuẩn vừa nêu** thay dòng schemaLocation đơn trong snippet ngắn nếu IDE kiểm tra XML/XSD chặt chẽ. Maven nhận biết POM theo namespace và nội dung chính; compiler/build behavior không phụ thuộc vào việc IDE có đang tải XSD hay không.

### 6.4. Java code của optional-helper

Tạo **optional-helper/src/main/java/dev/example/helper/FeatureHelper.java**:

~~~java
package dev.example.helper;

public final class FeatureHelper {
    private FeatureHelper() {
    }

    public static String decorate(String text) {
        return text + " [extra]";
    }
}
~~~

Đây là Java 17 hợp lệ, không cần bất kỳ dependency bên ngoài. FeatureHelper chỉ có tác dụng biến một chuỗi đầu vào thành chuỗi có hậu tố **[extra]**.

### 6.5. POM của feature-lib: điểm chính của bài

Tạo **feature-lib/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>optional-dependency-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>feature-lib</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>optional-helper</artifactId>
            <version>1.0.0</version>
            <scope>compile</scope>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
~~~

Tại đây, quan hệ **feature-lib → optional-helper** là dependency trực tiếp của feature-lib. `optional=true` ảnh hưởng quá trình tiêu thụ *feature-lib* từ project khác, **không khiến feature-lib phải bỏ dependency khi tự compile**.

Nếu feature-lib được phát hành lên Maven repository, POM được publish phải duy trì phần khai báo optional để người tiêu thụ nhận đúng metadata dependency. Tài liệu của thư viện nên nói rõ: ai dùng chức năng mở rộng phải khai báo optional-helper.

### 6.6. Java code của feature-lib

Tạo **feature-lib/src/main/java/dev/example/library/FeatureLibrary.java**:

~~~java
package dev.example.library;

import dev.example.helper.FeatureHelper;

public final class FeatureLibrary {
    private FeatureLibrary() {
    }

    public static String basic(String name) {
        return "Hello, " + name;
    }

    public static String extra(String name) {
        return FeatureHelper.decorate(basic(name));
    }
}
~~~

Giải thích:

- `basic` chỉ sử dụng Java standard library.
- `extra` gọi một class thuộc optional-helper.
- Cả hai method đều nhận và trả về `String`, vì vậy public method signatures **không buộc ConsumerApp tham chiếu trực tiếp đến kiểu của helper**.
- Maven compile feature-lib được vì module này **trực tiếp** nhận optional-helper ở compile classpath.

**Trong hệ thống lớn**, nên cân nhắc đưa implementation cần helper vào class adapter riêng, để giảm rủi ro class loading/initialization ngoài ý muốn. Ví dụ tập trung vào cơ chế Maven optional với ít code nhất.

### 6.7. POM của consumer-app: không khai báo helper

Tạo **consumer-app/pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>dev.example</groupId>
        <artifactId>optional-dependency-demo</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>consumer-app</artifactId>

    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>feature-lib</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
~~~

ConsumerApp chỉ biết rằng nó muốn dùng feature-lib. Maven **không** tự biến optional-helper thành dependency bắc cầu của consumer-app qua nhánh này.

### 6.8. Java code của consumer-app

Tạo **consumer-app/src/main/java/dev/example/consumer/ConsumerApp.java**:

~~~java
package dev.example.consumer;

import dev.example.library.FeatureLibrary;

public final class ConsumerApp {
    private ConsumerApp() {
    }

    public static void main(String[] args) {
        String name = "Mai";

        if (args.length > 0 && "extra".equals(args[0])) {
            System.out.println(FeatureLibrary.extra(name));
        } else {
            System.out.println(FeatureLibrary.basic(name));
        }
    }
}
~~~

Ứng dụng không import `FeatureHelper`. Câu lệnh gọi `FeatureLibrary.extra` chỉ thực hiện khi truyền đối số **extra**. Khi dùng nhánh basic, ứng dụng không cần thực thi implementation liên quan helper.

### 6.9. Build từ thư mục gốc

Yêu cầu: **JDK 17+**, Maven 3.9+ với repositories cần thiết có thể truy cập. Từ thư mục **optional-dependency-demo/** chạy:

~~~bash
mvn -version
mvn clean install
~~~

**install** chạy lifecycle đến pha install cho parent và các module, tạo artifact JAR/POM rồi đưa chúng vào **local Maven repository**. Dùng install trong demo để sau đó có thể chạy `dependency:tree` riêng cho consumer-app mà vẫn phân giải được các sibling modules. Khi chỉ cần build reactor, `mvn clean package` cũng biên dịch được các module, nhưng không bảo đảm POM/JAR của sibling modules đã nằm trong local repository cho một lệnh độc lập sau đó.

Build thành công thường tạo:

~~~text
optional-helper/target/optional-helper-1.0.0.jar
feature-lib/target/feature-lib-1.0.0.jar
consumer-app/target/consumer-app-1.0.0.jar
~~~

Các JAR thông thường **không phải fat/uber JAR**. Việc Maven phân giải dependencies vào classpath của một goal không có nghĩa `java -jar consumer-app-1.0.0.jar` tự có classpath gồm mọi JAR thư viện.

### 6.10. Quan sát dependency tree của từng module

Sau khi `mvn clean install` hoàn tất, chạy từ project root:

~~~bash
mvn -f feature-lib/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
mvn -f consumer-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Ở module **feature-lib**, dependency tree có thể thể hiện nhánh:

~~~text
dev.example:feature-lib:jar:1.0.0
\- dev.example:optional-helper:jar:1.0.0:compile
~~~

Ở **consumer-app**, nhánh chính chỉ cần:

~~~text
dev.example:consumer-app:jar:1.0.0
\- dev.example:feature-lib:jar:1.0.0:compile
~~~

**optional-helper không xuất hiện trong consumer dependency tree qua feature-lib**, trong khi nó vẫn là dependency trực tiếp của feature-lib. Một số phiên bản/cách xuất tree có thể hiển thị thêm metadata optional, còn prefix logging khác nhau; các khối trên minh họa **đồ thị phụ thuộc**, không phải stdout cố định của Maven.

Lệnh `dependency:tree` là cách kiểm chứng tốt hơn việc chỉ đọc POM: nó giúp nhìn rõ dependency thực tế khi kết hợp scopes, optional, exclusions và version mediation.

### 6.11. Chạy basic mà không đưa helper vào classpath của ứng dụng

Vì đây là các JAR/class directories thông thường, ta minh họa bằng classpath **tự nêu rõ**.

Linux/macOS (dùng dấu hai chấm làm phân cách classpath):

~~~bash
java -cp "consumer-app/target/classes:feature-lib/target/classes" dev.example.consumer.ConsumerApp
~~~

Windows PowerShell hoặc Command Prompt (dùng dấu chấm phẩy):

~~~powershell
java -cp "consumer-app\target\classes;feature-lib\target\classes" dev.example.consumer.ConsumerApp
~~~

Stdout chính xác với nhánh basic:

~~~text
Hello, Mai
~~~

Hai lệnh ứng với **hai hệ điều hành khác nhau**, không cần chạy cả hai. Trong classpath minh họa không có optional-helper. Đó là lựa chọn thủ công nhằm phản ánh classpath của consumer chỉ cần feature-lib; để xét *Maven dependency graph* thực sự, dựa vào `dependency:tree` như mục trước.

**Đừng nhầm:** `java -cp` chạy bằng classpath do người dùng truyền, **không tự gọi Maven dependency resolver**. Maven quản lý classpath khi chạy các Maven plugin goals thích hợp; Java launcher độc lập không tự đọc pom.xml.

### 6.12. Khi consumer gọi tính năng extra nhưng helper không có mặt

Có thể thử cùng classpath chưa có helper:

Linux/macOS:

~~~bash
java -cp "consumer-app/target/classes:feature-lib/target/classes" dev.example.consumer.ConsumerApp extra
~~~

Windows:

~~~powershell
java -cp "consumer-app\target\classes;feature-lib\target\classes" dev.example.consumer.ConsumerApp extra
~~~

Đường chạy này cố gọi `FeatureHelper.decorate`, nhưng optional-helper không nằm trong classpath chỉ định. Kết quả **không phải một thông báo fallback mặc định**: Java có thể phát sinh lỗi thiếu class như `NoClassDefFoundError` khi thực sự liên kết/tải lớp cần thiết. Chi tiết stack trace phụ thuộc JVM và vị trí class resolution; không nên lấy một stack trace cụ thể làm stdout bắt buộc.

Điều này cho thấy **optional chỉ xử lý dependency transitivity, không bảo đảm feature hoạt động nếu thiếu dependency runtime**. Nếu cần lỗi thân thiện, thư viện phải thiết kế adapter, phát hiện classpath hoặc xác thực precondition của riêng nó.

## 7. Consumer chủ động bổ sung optional-helper khi cần extra

Ứng dụng quyết định sử dụng tính năng mở rộng thì **tự khai báo optional-helper** trong **consumer-app/pom.xml**:

~~~xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>feature-lib</artifactId>
        <version>1.0.0</version>
    </dependency>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>optional-helper</artifactId>
        <version>1.0.0</version>
    </dependency>
</dependencies>
~~~

Đây là **đoạn thay thế nguyên khối <dependencies> của consumer-app**, không phải thêm một đoạn `<dependencies>` thứ hai trong cùng POM.

Sau khi cập nhật POM:

~~~bash
mvn clean install
mvn -f consumer-app/pom.xml org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Tree của consumer-app giờ có hai dependency trực tiếp:

~~~text
dev.example:consumer-app:jar:1.0.0
+- dev.example:feature-lib:jar:1.0.0:compile
\- dev.example:optional-helper:jar:1.0.0:compile
~~~

Chạy Java với helper được đưa vào classpath thủ công.

Linux/macOS:

~~~bash
java -cp "consumer-app/target/classes:feature-lib/target/classes:optional-helper/target/classes" dev.example.consumer.ConsumerApp extra
~~~

Windows:

~~~powershell
java -cp "consumer-app\target\classes;feature-lib\target\classes;optional-helper\target\classes" dev.example.consumer.ConsumerApp extra
~~~

Stdout chính xác:

~~~text
Hello, Mai [extra]
~~~

**Đây là cách opt-in đúng:** ứng dụng tự chọn dependency feature nó thực sự cần. Nó không cần đổi source của feature-lib hay bỏ optional ở POM của thư viện.

Khi phát hành và tiêu thụ qua Maven repository, app chỉ cần dependency trực tiếp tương ứng với tọa độ helper, và Maven sẽ quản lý classpath của các plugin theo resolution. Với plain Java launcher, app vẫn phải cung cấp các JAR thật trong runtime classpath hoặc xây dựng dạng distribution/fat JAR đúng cách.

## 8. Đối chiếu optional với scope

`scope` và `optional` có liên quan đến classpath/transitivity nhưng không đồng nghĩa.

| Khai báo trong B→C | C dùng cho chính B | C có tự đến A qua B không? | Khi dùng |
| --- | --- | --- | --- |
| **compile**, không optional | Compile/test/runtime classpaths phù hợp | Thường có, theo quy tắc transitivity | Dependency phổ biến của thư viện |
| **compile + optional=true** | Compile/test/runtime phù hợp của B | **Không qua B→C** | Feature không bắt buộc ở mọi consumer |
| **runtime**, không optional | Runtime và test của B; thường không cần để compile B | Có thể được truyền tới runtime/test của A | Dependency chỉ cần khi chạy |
| **runtime + optional=true** | Runtime/test của B | **Không qua B→C** | Runtime provider tùy chọn |
| **test** | Test compile/test runtime của B | Không truyền cho A theo cách dependency sản phẩm | JUnit, Mockito hoặc fixture library |
| **provided** | Compile/test của B, kỳ vọng môi trường cung cấp ở runtime | Không truyền theo kiểu compile thông thường | API do server/container cung cấp |

**Tại sao không dùng test scope thay optional?** Nếu `FeatureLibrary.extra` là chức năng **production** của B, B cần helper khi biên dịch mã sản phẩm. Đặt C thành `test` sẽ không đủ classpath compile cho **feature-lib**. `optional=true` giữ dependency cần thiết ở B mà không buộc mọi consumer tải C qua nhánh này.

**Tại sao không dùng provided thay optional?** `provided` thể hiện hợp đồng rằng môi trường runtime (container, JDK hoặc nền tảng khác) sẽ cung cấp dependency. Nó không đơn giản có nghĩa “consumer muốn thì cài, không muốn thì thôi”. Dùng sai provided dễ làm B compile được nhưng runtime thiếu JAR.

**Scope của A khi A tự khai báo C** thuộc quyền quyết định của A. Đừng mặc định phải sao chép `scope=compile` hay optional flag từ khai báo của B. Hãy chọn scope theo cách A thực sự dùng C.

## 9. optional khác exclusions thế nào?

Hai cơ chế đều có thể ngăn một dependency đi vào graph theo một nhánh nhưng **người ra quyết định và nơi khai báo khác nhau**.

### 9.1. Optional: tác giả thư viện chủ động

Trong **feature-lib**:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>optional-helper</artifactId>
    <version>1.0.0</version>
    <optional>true</optional>
</dependency>
~~~

Ý nghĩa: **tác giả feature-lib** tuyên bố helper chỉ phục vụ tính năng tùy chọn, không muốn ép mọi consumer nhận helper.

### 9.2. Exclusion: ứng dụng tiêu thụ chặn một nhánh

Giả sử thư viện khác **legacy-lib** phụ thuộc **legacy-helper** theo nhánh thông thường, và consumer không cần chức năng đó. Consumer có thể loại trừ dependency từ nhánh legacy-lib bằng:

~~~xml
<dependency>
    <groupId>dev.example</groupId>
    <artifactId>legacy-lib</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>dev.example</groupId>
            <artifactId>legacy-helper</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là **đoạn XML minh họa, không phải project đã xây ở trên**; legacy-lib/legacy-helper chỉ là tên trong tình huống giả định.

Khác biệt:

| Tiêu chí | optional | exclusions |
| --- | --- | --- |
| Ai thường khai báo? | Tác giả thư viện B | Bên tiêu thụ A |
| Khai báo ở đâu? | Dependency B→C trong POM B | Trên dependency A→B trong POM A |
| Ý định | C chỉ phục vụ một phần chức năng của B | A không muốn một transitive dependency đi qua nhánh đã chọn |
| Có loại C khỏi build của B? | Không | Không; chỉ ảnh hưởng đường resolve của A theo nhánh khai báo |
| Có đảm bảo C vắng khỏi toàn bộ A không? | Không nếu A có nhánh/direct dependency khác | Cũng không nếu C đến từ nhánh khác |
| Bảo trì | Tác giả B chịu trách nhiệm tài liệu hóa | A chịu trách nhiệm chặn đường dependency phù hợp |

**Không nên lạm dụng exclusions.** Nếu thư viện B thật sự bắt buộc phải có C để chạy, consumer loại C chỉ để bớt JAR có thể gây lỗi runtime. Nếu C là feature tùy chọn thực sự, tác giả B nên đánh dấu optional hoặc tách module thay vì buộc mọi consumer tự thêm exclusions.

## 10. optional khác dependencyManagement và BOM

**dependencyManagement** chỉ định quy tắc quản lý dependency như version/scope/exclusions cho những dependency phù hợp được sử dụng. Nó **không tự thêm dependency vào classpath của một project** nếu project không phụ thuộc vào artifact đó.

Ví dụ parent POM hoặc BOM có thể quản lý optional-helper:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>dev.example</groupId>
            <artifactId>optional-helper</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Sau khi có management, consumer muốn dùng helper vẫn phải khai báo trực tiếp:

~~~xml
<dependencies>
    <dependency>
        <groupId>dev.example</groupId>
        <artifactId>optional-helper</artifactId>
    </dependency>
</dependencies>
~~~

Version có thể được điền từ dependencyManagement của consumer. **Không có chuyện chỉ import BOM là C tự xuất hiện**, cũng không có chuyện BOM tự hủy tính optional của một quan hệ B→C mà không có lý do trong effective graph.

**Import BOM** qua dependencyManagement với `type=pom`, `scope=import` giúp nhập các managed entries; nó khác hoàn toàn việc khai báo B→C là optional trong **dependencies** của B.

Trong một số hệ thống có parent dependencyManagement chứa các trường được quản lý phức tạp, để xác định graph cuối cùng phải xem **effective POM của project đang tiêu thụ** và **dependency:tree**. Đừng gộp kết luận về version management với kết luận về optional transitivity.

## 11. Optional, transitive graph và nhiều đường đưa C vào A

Hãy mở rộng tình huống:

~~~text
                 +--> B (feature-lib) ---optional---> C (helper)
                 |
A (consumer-app)-+
                 |
                 +--> D (another-lib) --------------> C (helper)
~~~

B→C optional **không cấm** D→C được resolve nếu D→C là quan hệ bắc cầu hợp lệ theo scope và các quy tắc khác. Vì thế, A có thể vẫn nhận C mà không khai báo C trực tiếp.

Điều này quan trọng khi debug: một project có thể “chạy được” vì C tình cờ đến từ D. Sau khi D cập nhật và bỏ dependency C, tính năng extra của B đột nhiên lỗi. Để tránh phụ thuộc vào đường transitive tình cờ, **project A phải trực tiếp khai báo dependency C nếu source/runtime của nó cố ý sử dụng feature cần C**.

Tương tự, một dependency được optional ở nhánh này không làm C trở thành forbidden hoặc excluded global. Maven giải quyết graph từ **tất cả** các nhánh đủ điều kiện.

**Version conflicts:** nếu A khai báo C trực tiếp một version khác với version mà B được compile, Maven có thể chọn version do A khai báo theo cơ chế dependency mediation và quản lý dependency. Khi thay version, phải xác nhận tương thích binary/API, vì biên dịch B với C version cũ không bảo đảm B hoạt động với C version mới ở runtime. Có thể gặp `NoSuchMethodError`, `ClassNotFoundException` hoặc lỗi liên kết khác khi khác biệt API không tương thích.

## 12. Không nhầm optional metadata với đóng gói fat JAR

Một điều thường khiến người mới khó hiểu:

**Trong POM B**, C optional là một quyết định **dependency graph**.

**Trong JAR B**, class files đã compile vẫn có thể tham chiếu đến classes từ C. Plain JAR của Maven JAR Plugin **không tự nhét C vào JAR B** chỉ vì B dùng C; muốn đóng gói kèm mọi dependency phải cấu hình công cụ distribution/assembly/shading hoặc packaging chuyên biệt.

Khi xây ứng dụng A thành **fat JAR**, plugin tạo fat JAR thường lấy dependencies từ **đồ thị đã resolve của A**. Nếu C bị ngắt bởi optional B→C và A không có nhánh khác đưa C vào, C thường không có trong input dependency graph để đưa vào fat JAR. Khi tính năng extra được gọi, có thể thiếu C.

**Không suy ra một JAR chứa C bằng cách kiểm tra tên file.** Cần xem dependency tree, nội dung JAR/assembly, manifest và đường chạy thực tế. Với Spring Boot, Shade hay Assembly, chi tiết classpath/packaging còn phụ thuộc plugin configuration cụ thể.

## 13. Tác động tới API và runtime behavior của thư viện

Một thư viện có optional dependency muốn an toàn cần thiết kế boundary.

### 13.1. Tránh để API bắt buộc phụ thuộc vào kiểu của C

Ví dụ thiết kế dễ gây rắc rối (chỉ để cảnh báo, không phải code đầy đủ):

~~~java
public ThirdPartyResult parse(ThirdPartyParser parser) {
    return parser.parse();
}
~~~

Nếu `ThirdPartyParser` và `ThirdPartyResult` là classes thuộc C, consumer muốn sử dụng/chỉ load API này có thể phải có C ở compile/runtime, ngay cả khi chỉ muốn một phần API khác. Điều này làm ý nghĩa optional kém rõ.

Một chiến lược tốt hơn:

- API core sử dụng JDK types/kiểu do chính B định nghĩa.
- Adapter có C-specific API nằm trong class/package/module riêng.
- Tài liệu chỉ rõ feature adapter cần dependency nào, version/scope nào.
- Test riêng kịch bản classpath **có** và **không có** C.

### 13.2. Không buộc class core load C khi khởi tạo

Nếu B có static initializer gọi C, hoặc phần khởi động luôn tạo adapter cần C, consumer có thể lỗi dù không dùng feature. Optional không sửa lỗi class loading tự động.

Đặt việc khởi tạo feature sau một bước lựa chọn rõ, hoặc tách adapter module. Với một số thư viện hỗ trợ ServiceLoader/Reflection, có thể phát hiện provider hiện diện và đưa thông báo phù hợp; tuy nhiên phải kiểm tra exception handling, không coi việc bắt mọi `NoClassDefFoundError` là cách thiết kế an toàn.

### 13.3. Tách module là lựa chọn được Apache Maven khuyến nghị cân nhắc

Thay vì một B monolith có nhiều dependencies optional, có thể có:

~~~text
feature-core
   ^
   |
feature-adapter-extra ---> helper-C

consumer-app ---> feature-core
consumer-extra -> feature-adapter-extra
~~~

Với cấu trúc này, module adapter có dependency bình thường vào C; consumer chọn **module adapter** là chọn toàn bộ chức năng extra và các dependency bắt buộc của nó. Cấu trúc module làm hợp đồng rõ hơn, hỗ trợ test và phát hành độc lập.

Optional là một giải pháp hữu ích khi **không thể hoặc chưa hợp lý để tách module**, nhưng không phải luôn là kiến trúc ưu tiên.

## 14. Cách dùng optional khi phát hành thư viện ra repository

Một người tiêu thụ không đọc source code B; họ phụ thuộc vào **tọa độ Maven** của B và thông tin dependency trong **POM được publish cùng artifact**.

Quy trình thông thường:

1. Tác giả B khai báo C trong `<dependencies>` với `<optional>true</optional>`.
2. B được build và publish vào Maven repository cùng POM.
3. A khai báo trực tiếp B.
4. Maven resolve POM B, thấy B→C optional và không truyền C qua đường này.
5. Nếu A cần feature extra, A khai báo C trực tiếp hoặc dùng module adapter theo tài liệu B.
6. A xác minh dependency tree và artifact runtime của chính nó.

Nếu một công cụ publish, flatten POM hoặc repository metadata generator thay đổi/loại bỏ thẻ optional ngoài ý muốn, consumer có thể nhận graph khác. Vì vậy tác giả thư viện nên kiểm tra **published POM** hoặc thử một consumer project thật sau khi phát hành bản thử nghiệm, không chỉ đọc POM nguồn trong repository.

Những hệ build khác Maven có metadata/logic xử lý riêng, nên không được kết luận rằng mọi Gradle/Ivy/SBT consumer sẽ tái hiện chính xác cấu trúc optional của Maven mà không kiểm chứng. Khi cross-build-tool, cần kiểm tra metadata được publish và dependency graph của consumer thực tế.

## 15. Kiểm thử hai kịch bản consumer: không dùng C và có dùng C

Muốn đánh dấu C là optional một cách an toàn, CI của tác giả thư viện nên kiểm tra ít nhất hai đường tiêu thụ.

### Kịch bản 1 – basic consumer

- POM consumer chỉ khai báo B.
- Dependency tree của consumer không có C **qua nhánh B→C**.
- Source consumer sử dụng feature basic, biên dịch và chạy được với classpath không có C.
- Không có static initializer hoặc classpath scanning ngầm làm feature basic bắt buộc C.

### Kịch bản 2 – extra consumer

- POM consumer khai báo B và C (hoặc module adapter tương ứng).
- Dependency tree có C ở version tương thích.
- Consumer compile/test và chạy đúng feature cần C.
- Nếu C nâng version, test tương thích binary/API.

### Kịch bản 3 – phát hành/truyền metadata

- Thử build như người dùng bên ngoài repository.
- Quan sát POM published và dependency graph của một project hoàn toàn mới.
- Kiểm tra cả trường hợp C có thể vào graph từ một dependency D khác, tránh dựa vào đường đó.
- Kiểm tra packaging (JAR/fat JAR/container) thực tế mà người dùng deploy.

**Phần mềm B tự chạy được với C không đủ** để kết luận optional đã an toàn cho A. Lỗi optional thường chỉ xuất hiện khi consumer thiếu dependency mà tác giả B mặc nhiên nghĩ luôn có.

## 16. Những lỗi dễ gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Build B thành công nhưng A thiếu class từ C | B→C optional, A chưa khai báo C | Xem POM B, `dependency:tree` A, thêm C trực tiếp nếu A dùng feature |
| A dùng feature basic nhưng vẫn lỗi thiếu C | Core API/static init của B tham chiếu C sớm | Phân tích class loading, tách adapter hoặc sửa thiết kế |
| A tưởng C bị loại hoàn toàn nhưng nó vẫn xuất hiện | C được đưa từ nhánh D khác hoặc A trực tiếp khai báo | Xem full dependency tree của A |
| Test của B pass nhưng A lỗi runtime | Test B luôn có C vì B có direct dependency | Test consumer độc lập **không có C** |
| A thêm C rồi gặp NoSuchMethodError | Version C không tương thích với B | Khóa/chọn version tương thích, kiểm tra dependency mediation |
| B đánh dấu C test scope để tránh transitive, B compile fail | C cần cho production source của B | Dùng scope đúng; nếu chỉ optional cho consumer thì đặt optional=true |
| Dùng provided nhưng server không cấp C | Nhầm provided với optional | Chọn optional/adapter hoặc bảo đảm runtime container thật có C |
| POM có dependencyManagement của C nhưng A không nhận C | Management không thêm dependency | A khai báo trực tiếp C, nhận version từ management nếu phù hợp |
| Dependency optional xuất hiện trong JAR B? | Nhầm class code với JAR dependency packaging | Kiểm tra nội dung artifact, plugin tạo distribution |
| Consumer đặt exclusion trên B rồi vẫn có C | C đến từ nhánh khác | Kiểm tra graph đầy đủ, exclusions theo nhánh |
| IDE hiển thị C ở build B, nhưng dependency tree A không có | Khác góc nhìn project owner và consumer | So sánh `dependency:tree` của từng module |
| CLI java không thấy B dù Maven build được | `java -cp` không tự đọc pom.xml | Cung cấp runtime classpath hoặc dùng distribution đúng |
| Published POM không có optional=true | Publish/flatten/metadata không bảo tồn thông tin | Kiểm tra POM trong artifact repository |
| Tính năng thêm adapter mới kéo nhiều dependency không cần | B monolith có quá nhiều optional features | Tách core/adapter modules |
| Chỉ thêm `<optional>true</optional>` vào A→B và kỳ vọng A không phụ thuộc B | Optional ảnh hưởng **consumer của A**, không xóa dependency trực tiếp A→B | Hiểu hướng transitivity và vị trí khai báo |

**Điều tra hiệu quả:** xác định **project đang build** (A hay B), **cạnh dependency nào được đánh dấu optional**, và **classpath ở thời điểm compile/test/runtime**. Ba thông tin này thường chỉ ngay nguyên nhân.

## 17. Quy trình chẩn đoán Maven dependency tree

Từ project consumer khi dependencies đã phân giải được:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree
~~~

Có thể lọc theo groupId để tập trung:

~~~bash
mvn org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree -Dincludes=dev.example
~~~

Các dòng `dependency:tree` báo những dependencies có thể resolve trong model theo rules hiện tại. Không kết luận rằng C bị ẩn bởi `-Dincludes` chỉ vì nó không hiện: hãy chạy một lần full tree khi cần kiểm chứng.

Kiểm tra POM hiệu lực:

~~~bash
mvn help:effective-pom
~~~

Xác minh C được đánh dấu optional ở **B**: đọc POM B hoặc POM được publish cùng artifact. Đọc hiệu lực ở A để xác định các direct dependencies và managed versions; sau đó xem graph A. POM A không nhất thiết có một dòng explicit nói “C bị bỏ vì optional của B”; dependency tree mới thể hiện C không thuộc graph được resolve qua nhánh B.

Khi cần xem source của dependency hiện hành, kiểm tra groupId, artifactId, version, classifier và type. Một artifact với classifier khác không nhất thiết cùng cách dùng với artifact chính.

**Không tự sửa bằng cách xóa tất cả exclusions hoặc ép version mới nhất** trước khi biết class nào thực sự bị thiếu. Lỗi binary incompatibility khác lỗi dependency không có mặt.

## 18. Quy tắc lựa chọn optional hay module tách riêng

Có thể áp dụng một cây quyết định:

~~~text
C có bắt buộc cho mọi chức năng của B?
  |
  +-- Có  --> Giữ dependency thường, chọn scope phù hợp.
  |
  +-- Không
        |
        +-- Có thể tách feature B thành module adapter riêng?
        |      |
        |      +-- Có --> Tách core + adapter với dependency thường.
        |      |
        |      +-- Chưa thể
        |             |
        |             +-- B có API/core chạy được khi thiếu C?
        |                      |
        |                      +-- Có --> Cân nhắc optional=true,
        |                      |          document consumer opt-in, test 2 classpaths.
        |                      |
        |                      +-- Không --> Cần sửa kiến trúc hoặc giữ dependency thường.
~~~

Đừng chọn optional chỉ vì một dependency có dung lượng lớn hoặc giấy phép khó dùng mà không xem hậu quả. Nó có thể tiết kiệm dependency ở consumer không cần feature, nhưng nếu feature thật sự bắt buộc hoặc core code khởi tạo cần C, việc đánh optional sẽ chuyển lỗi từ build B sang runtime A.

## 19. Bài tập đọc POM và giải đáp

Giả sử POM của **report-lib** khai báo:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>csv-engine</artifactId>
        <version>2.0.0</version>
        <optional>true</optional>
    </dependency>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>core-utils</artifactId>
        <version>1.3.0</version>
    </dependency>
</dependencies>
~~~

Ứng dụng **report-app** chỉ khai báo **report-lib** làm dependency compile.

**Câu 1:** Khi tự build report-lib, csv-engine có mặt trong compile classpath không?

**Đáp:** Có theo scope mặc định compile của chính report-lib. `optional=true` không xóa direct dependency của report-lib.

**Câu 2:** Khi report-app resolve report-lib, csv-engine có tự được truyền qua quan hệ report-lib→csv-engine không?

**Đáp:** Không. Đường phụ thuộc đó được đánh dấu optional. Report-app có thể nhận core-utils theo quan hệ bắc cầu thông thường nếu không bị scope/exclusions khác ngăn.

**Câu 3:** Report-app dùng tính năng CSV và gọi code của report-lib cần csv-engine. Cần làm gì?

**Đáp:** Report-app phải khai báo csv-engine trực tiếp ở phiên bản/scope tương thích hoặc dùng module adapter được tác giả report-lib cung cấp.

**Câu 4:** Report-app lại phụ thuộc another-lib và another-lib kéo csv-engine transitively. Có thể csv-engine vẫn xuất hiện trong report-app không?

**Đáp:** Có. Optional ở một nhánh không phải global exclusion.

**Câu 5:** Đặt csv-engine trong dependencyManagement của report-app có làm nó tự được tải vào classpath không?

**Đáp:** Không. DependencyManagement chỉ quản lý thông tin khi dependency được sử dụng/được resolve theo những đường phù hợp; muốn opt-in, report-app cần dependency declaration tương ứng.

**Câu 6:** Đổi csv-engine trong report-lib từ compile/optional sang provided để tránh người tiêu thụ tải có tương đương không?

**Đáp:** Không. Provided thể hiện mong đợi môi trường cấp dependency ở runtime và có classpath rules khác. Chỉ dùng khi hợp đồng môi trường thực sự phù hợp.

**Câu 7:** Kiểm tra hiệu lực bằng cách nào?

**Đáp:** Chạy dependency tree của report-lib và report-app, xem khai báo optional trong POM của report-lib được publish, kiểm tra classpath/test của consumer với và không có csv-engine.

## 20. Checklist review một dependency optional trước khi phát hành

1. **Xác định B và C**: C phục vụ chức năng nào, thật sự không bắt buộc với mọi consumer?
2. **Giữ scope đúng** của B→C (compile/runtime/provided/test) theo nhu cầu của chính B.
3. **Đặt optional tại khai báo B→C**, không ở vị trí tùy tiện của project khác.
4. **Kiểm tra API/initialization của B** để đường code core không cần C.
5. **Tài liệu hóa cách consumer khai báo trực tiếp C**, version tương thích và feature cần opt-in.
6. **Chạy full dependency:tree cho B**: xác nhận B vẫn có C như dự kiến.
7. **Chạy full dependency:tree cho consumer chỉ có B**: xác nhận C không tự vào qua nhánh B.
8. **Chạy consumer basic không có C**: build và runtime phải ổn.
9. **Thêm C trực tiếp ở consumer và chạy feature mở rộng**: kiểm tra tương thích API/binary.
10. **Kiểm tra nhánh dependency khác** có vô tình đưa C vào không.
11. **Đọc published POM/metadata** sau deploy để xác nhận optional được giữ.
12. **Kiểm tra distribution artifact** (JAR/fat JAR/container) và classpath cuối.
13. **Ưu tiên tách module adapter** nếu optional dependencies ngày càng nhiều hoặc API bị ràng buộc vào C.
14. **Đừng lạm dụng optional để giấu dependency bắt buộc** hoặc né giải quyết version/license/security issues.

## Tài liệu chính thức

- [Apache Maven — Introduction to Optional Dependencies and Dependency Exclusions](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)

**Kết luận:** Maven `<optional>true</optional>` nói rằng **tác giả thư viện B vẫn cần dependency C**, nhưng **không muốn mọi dự án tiêu thụ B tự động nhận C**. Người tiêu thụ phải khai báo C khi chủ động sử dụng feature cần C. Để dùng optional an toàn, hãy kết hợp POM metadata chính xác, API có ranh giới rõ, dependency tree kiểm chứng và test consumer cả hai trường hợp có/không có C.
