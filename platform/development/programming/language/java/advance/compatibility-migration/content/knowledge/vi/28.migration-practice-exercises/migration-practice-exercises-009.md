# Chuyển dự án dùng JAXB khỏi dependency ngầm vào JDK

## 1. Bối cảnh và mục tiêu bài thực hành

Một dự án Java được phát triển trên JDK 8 có thể sử dụng JAXB (Java Architecture for XML Binding) chỉ bằng các lệnh import như `javax.xml.bind.JAXBContext`, `javax.xml.bind.Marshaller` và `javax.xml.bind.annotation.XmlRootElement`. Khi đó, một số thành phần JAXB được cung cấp cùng bản phân phối JDK 8; file `pom.xml` hoặc `build.gradle` có thể **không khai báo JAXB** mà chương trình vẫn compile và chạy.

Khi chuyển sang JDK 11, 17 hoặc 21, giả định đó không còn đúng. Theo **JEP 320**, JDK 11 đã loại bỏ các module Java EE/CORBA từng được bundled, trong đó có JAXB và JAX-WS. JDK mới vẫn có XML parsers, DOM, SAX, StAX và nhiều API Java SE khác, nhưng **không tự cung cấp JAXB API cùng runtime implementation như mô hình JDK 8**.

Bài thực hành này hướng dẫn cách:

1. Tạo một dự án JAXB tối giản để tái hiện dependency ngầm vào JDK 8.
2. Chạy nguyên artifact trên JDK mới và phân biệt lỗi biên dịch với lỗi runtime.
3. Khai báo **JAXB API** và **JAXB runtime provider** như các dependency tường minh.
4. Chọn một trong hai chiến lược: **giữ `javax.xml.bind`** ở nhánh JAXB 2.3 hoặc **chuyển sang `jakarta.xml.bind`** ở JAXB 3/4.
5. Kiểm thử marshal/unmarshal bằng dữ liệu thực, kiểm tra transitive dependencies và artifact đóng gói.
6. Xử lý XJC/generated code, Activation, JPMS, classloader và bảo mật XML.
7. Hoàn thiện tiêu chí kiểm chứng migration, CI và rollback.

Đây là một bài lab để **thực hiện trong môi trường riêng**. Các lệnh trong tài liệu là hướng dẫn thực hành, không phải kết quả chạy thử đã được xác nhận trong hệ thống của người đọc. Khi áp dụng vào production, hãy dùng version chính thức được framework/vendor hỗ trợ và chính sách dependency của tổ chức.

### Kết quả mong đợi

Sau bài thực hành:

- Ứng dụng JAXB không còn phụ thuộc vào một module JAXB ngầm định trong JDK.
- Compile classpath có JAXB API phù hợp với source.
- Runtime classpath chứa provider tương thích nếu ứng dụng tự chạy JAXB.
- Code có kiểm thử round-trip XML và xử lý UTF-8 tường minh.
- Build/CI ghi rõ minimum JDK, dependency versions và cách đóng gói.
- Nhóm hiểu **khi nào chỉ bổ sung dependency là đủ** và khi nào bắt buộc phải đổi từ `javax` sang `jakarta`.

## 2. Kiến thức nền: JAXB API khác JAXB implementation

JAXB chuyển đổi qua lại giữa Java objects và XML, thường được gọi là:

- **Marshalling:** Java object → XML.
- **Unmarshalling:** XML → Java object.
- **Binding metadata:** annotation, mapping, namespace và schema information.
- **Provider/runtime:** implementation thực thi marshalling/unmarshalling.

Một ví dụ:

```java
JAXBContext context = JAXBContext.newInstance(Customer.class);
Marshaller marshaller = context.createMarshaller();
Unmarshaller unmarshaller = context.createUnmarshaller();
```

Các class như `JAXBContext` và `Marshaller` đến từ **API**. Để factory `JAXBContext.newInstance(...)` hoạt động, ứng dụng cần một **provider JAXB** tại runtime. Với các ứng dụng độc lập trên JDK 11+, provider phải được đưa vào classpath/module path theo một cách được hỗ trợ.

Sơ đồ:

```text
Java application
      |
      | compile: JAXB API annotations, JAXBContext, Marshaller
      v
JAXB API
      |
      | runtime: tìm JAXB provider
      v
JAXB implementation (ví dụ GlassFish JAXB Runtime)
      |
      v
XML parser / serializer / supporting libraries
      |
      v
XML files / streams / messages
```

Chỉ có JAXB API JAR thường tạo ra tình trạng **compile pass nhưng `JAXBContext.newInstance` fail**. Chỉ có provider mà thiếu API rõ ràng có thể khiến code không compile hoặc phụ thuộc vào transitive API không ổn định. Mục tiêu bài lab là khai báo cả hai vai trò một cách có chủ đích.

## 3. Lịch sử cần nhớ trước khi chọn phiên bản

| Mốc | Tình trạng JAXB và ý nghĩa migration |
|---|---|
| JDK 8 | Nhiều bản phân phối JDK cung cấp JAXB 2.x với `javax.xml.bind`, `xjc` và `schemagen` trong toolset |
| JDK 9 | JAXB là module liên quan Java EE, không còn mặc định được resolve như classpath Java 8 trong nhiều tình huống; từng có cách bật tạm bằng `--add-modules java.xml.bind` |
| JDK 10 | Còn giai đoạn chuyển tiếp, nhưng không nên xem module bundled là tương lai dài hạn |
| **JDK 11** | **JEP 320 loại bỏ `java.xml.bind` và các công cụ JAXB từng bundled** |
| JDK 17 | Không có JAXB bundled; ứng dụng phải quản lý API/provider ngoài JDK nếu dùng JAXB |
| JDK 21 | Tương tự: cần dependency bên ngoài; việc nâng JDK không tự chuyển `javax` sang `jakarta` |
| Jakarta XML Binding 2.3.x | Một số artifact mang tọa độ `jakarta.xml.bind` nhưng **vẫn xuất bản package `javax.xml.bind`** |
| Jakarta XML Binding 3.x/4.x | API chuyển sang package `jakarta.xml.bind`; không tương thích nhị phân với source/bytecode `javax` |

Điểm dễ nhầm nhất: **tên Maven artifact và namespace Java package không phải lúc nào cũng giống nhau**. Ví dụ, artifact `jakarta.xml.bind:jakarta.xml.bind-api:2.3.3` thuộc dòng 2.3 và cung cấp API có package `javax.xml.bind`. Dòng 4.x dùng `jakarta.xml.bind`. Không chọn phiên bản chỉ bằng cách nhìn tên groupId.

**Không thử giải pháp sau trên JDK 11/17/21:**

```bash
java --add-modules java.xml.bind -jar app.jar
```

JDK 11+ không còn module `java.xml.bind` trong runtime, vì vậy flag không thể hồi sinh thứ đã bị loại bỏ. Cần external dependencies hoặc migration thực sự.

## 4. Sơ đồ quyết định trước khi sửa source

```text
Ứng dụng đang dùng JAXB từ JDK 8
               |
               v
Source / generated code import javax.xml.bind?
               |
               +--- Có
               |     |
               |     v
               |   Framework hiện tại vẫn dùng javax?
               |     |
               |     +--- Có ---> Nhánh A: giữ javax, thêm JAXB 2.3 API/runtime
               |     |
               |     +--- Không ---> Nhánh B: nâng toàn stack sang jakarta
               |
               +--- Đã dùng jakarta
                     |
                     v
               Chọn JAXB 3/4 API/runtime đúng framework
               |
               v
         Build + runtime + XML contracts
               |
               v
          Test minimum supported JDK
```

**Nhánh A** thường là bước ít thay đổi nhất khi mục tiêu chỉ là đưa một Java 8 application cũ lên JDK 17/21 nhưng tiếp tục dùng framework `javax`.

**Nhánh B** phù hợp khi ứng dụng đang chuyển sang một framework/server thế hệ Jakarta, ví dụ một stack mới yêu cầu `jakarta.*`. Khi đó, việc chỉ thêm JAXB 2.3 không giải quyết API mismatch.

Đừng trộn các API/provider thuộc hai nhánh vào cùng runtime một cách vô tình. Hai class `javax.xml.bind.JAXBContext` và `jakarta.xml.bind.JAXBContext` là những binary names khác nhau.

## 5. Chuẩn bị môi trường lab

### 5.1. Yêu cầu

- JDK 8 để tái hiện baseline nếu có sẵn trong môi trường thực hành.
- JDK 17 hoặc 21 để kiểm tra runtime đích.
- Maven 3.x và Maven Wrapper (nếu dự án có).
- Một editor và terminal.
- Kết nối artifact repository được phép sử dụng.
- Một thư mục dự án trống.

Không cần dùng JDK 8 cho mọi bước nếu không còn sẵn JDK 8; có thể bắt đầu bằng một dự án `javax` hiện hữu. Nhưng baseline trên JDK 8 giúp thấy rõ dependency ngầm đã hình thành ra sao.

### 5.2. Cấu trúc dự án

```text
jaxb-migration-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/jaxb/
    │           ├── Customer.java
    │           └── App.java
    └── test/
        └── java/
            └── com/example/jaxb/
                └── JaxbRoundTripTest.java
```

Trong baseline, ta tạo hai class chính và chưa cần test dependency. Sau khi chuyển sang JDK mới, thêm test và runtime provider.

### 5.3. Kiểm tra JDK của process build

Ví dụ:

```bash
java -version
javac -version
mvn -version
```

Nếu dùng Maven Wrapper:

```bash
./mvnw -version
```

Trên PowerShell có thể dùng `.\mvnw.cmd -version`.

Chú ý `mvn -version` hiển thị Java runtime đang chạy Maven. Đây có thể khác JVM dùng chạy ứng dụng nếu launcher hoặc CI cấu hình riêng. Khi viết báo cáo migration, phải ghi **compiler JDK, build JVM và runtime JDK** nếu chúng không giống nhau.

## 6. Bước 1 — Tạo một model JAXB theo namespace javax

File `src/main/java/com/example/jaxb/Customer.java`:

```java
package com.example.jaxb;

import javax.xml.bind.annotation.XmlAccessType;
import javax.xml.bind.annotation.XmlAccessorType;
import javax.xml.bind.annotation.XmlElement;
import javax.xml.bind.annotation.XmlRootElement;
import javax.xml.bind.annotation.XmlType;

@XmlRootElement(name = "customer")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"name", "email"})
public class Customer {
    @XmlElement(required = true)
    private String name;

    @XmlElement(required = true)
    private String email;

    public Customer() {
        // JAXB cần constructor không tham số có thể truy cập.
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

Giải thích:

- `@XmlRootElement(name = "customer")` ánh xạ object thành phần tử root `<customer>`.
- `@XmlAccessorType(XmlAccessType.FIELD)` chỉ định JAXB truy cập các fields.
- `@XmlType(propOrder = ...)` giữ thứ tự các elements trong XML theo mapping đã định.
- `@XmlElement(required = true)` mô tả metadata/schema, **không nên coi đó là cơ chế tự động từ chối mọi XML không hợp lệ** nếu không cấu hình validation.
- Constructor không tham số phục vụ khả năng JAXB tạo object khi unmarshal.
- `javax.xml.bind.annotation.*` là API JAXB dòng cũ; phần này được giữ nguyên khi thực hiện nhánh A.

Đây là model đủ đơn giản để thấy tác dụng của dependency mà không bị các yếu tố khác như database hay SOAP framework che khuất.

## 7. Bước 2 — Viết chương trình marshal/unmarshal

File `src/main/java/com/example/jaxb/App.java`:

```java
package com.example.jaxb;

import java.io.StringReader;
import java.io.StringWriter;

import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;

public final class App {
    private App() {
    }

    public static void main(String[] args) throws Exception {
        Customer original = new Customer(
                "Nguyễn An",
                "an@example.test"
        );

        JAXBContext context = JAXBContext.newInstance(Customer.class);

        Marshaller marshaller = context.createMarshaller();
        marshaller.setProperty(
                Marshaller.JAXB_FORMATTED_OUTPUT,
                Boolean.TRUE
        );

        StringWriter xmlWriter = new StringWriter();
        marshaller.marshal(original, xmlWriter);

        String xml = xmlWriter.toString();
        System.out.println(xml);

        Unmarshaller unmarshaller = context.createUnmarshaller();
        Customer restored = (Customer) unmarshaller.unmarshal(
                new StringReader(xml)
        );

        System.out.println(
                "Round-trip: "
                + restored.getName()
                + " <" + restored.getEmail() + ">"
        );
    }
}
```

Một kết quả mong đợi **về nội dung**:

```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<customer>
    <name>Nguyễn An</name>
    <email>an@example.test</email>
</customer>
```

Format declaration, whitespace và attribute order phụ thuộc API/provider/configuration cụ thể; **không nên so sánh XML bằng chuỗi raw khi hợp đồng chỉ yêu cầu cùng cấu trúc và giá trị**.

Quan trọng: `StringWriter` giữ dữ liệu trong Java `String`. XML declaration có thể ghi UTF-8, nhưng điều đó không tự quyết định bytes khi ghi ra file. Phần file I/O ở cuối bài sẽ chỉ định `StandardCharsets.UTF_8` tường minh.

## 8. Bước 3 — Tái hiện sự phụ thuộc JAXB ngầm vào JDK 8

### 8.1. POM baseline mô phỏng dự án Java 8

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jaxb-migration-lab</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.source>8</maven.compiler.source>
        <maven.compiler.target>8</maven.compiler.target>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.8.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

POM này **không khai báo JAXB**. Khi compile trên JDK 8 có JAXB bundled, source `javax.xml.bind.*` vẫn có thể compile vì các APIs đang đến từ JDK.

Các versions và build settings trong mẫu phục vụ lab. Với một dự án thật, dùng Maven/Compiler Plugin version phù hợp theo support policy; không tự áp một POM cũ vào toàn bộ hệ thống.

### 8.2. Compile bằng JDK 8

Đảm bảo terminal/CI thực sự dùng JDK 8:

```bash
mvn -version
mvn clean package
```

Lệnh thử chạy class trong JAR:

```bash
java -cp target/jaxb-migration-lab-1.0.0.jar \
  com.example.jaxb.App
```

Chương trình có thể hoạt động mà **không có `jaxb-api.jar` hoặc `jaxb-runtime.jar`** trong POM. Chính đó là dependency ngầm ta cần loại bỏ khi migration.

### 8.3. Ghi baseline

Lưu:

- Maven và JDK versions.
- Artifact SHA-256.
- XML output mẫu và round-trip result.
- Encoding của XML khi xuất file thực.
- Các schema/XSD nếu ứng dụng sử dụng.
- Tập công nghệ phụ thuộc JAXB như SOAP, JPA converters, generated DTOs.

Nếu không có môi trường JDK 8, có thể bỏ qua bước tái hiện và bắt đầu từ class/pom hiện có, nhưng phải ghi baseline thực tế, không giả định đã chạy thử.

## 9. Bước 4 — Chạy nguyên artifact Java 8 trên JDK 17/21

**Không build lại ở bước này.** Ta muốn chứng minh tác động của runtime một cách độc lập.

Giả sử JAR vừa được tạo bằng JDK 8; dùng một terminal chỉ định runtime Java 17:

```bash
"$JAVA17_HOME/bin/java" -version
"$JAVA17_HOME/bin/java" \
  -cp target/jaxb-migration-lab-1.0.0.jar \
  com.example.jaxb.App
```

`JAVA17_HOME` là biến placeholder; thay bằng đường dẫn JDK thật.

Một triệu chứng có thể xuất hiện:

```text
java.lang.NoClassDefFoundError:
  javax/xml/bind/JAXBContext
```

hoặc `ClassNotFoundException` xuất hiện trong chain, tùy vị trí load class và cách launcher/framework xử lý.

### 9.1. Điều ta vừa chứng minh

- Class file Java 8 bản thân không nhất thiết bị từ chối bởi JVM Java 17/21.
- Ứng dụng gọi một class JAXB không còn nằm trong JDK runtime.
- Vấn đề đầu tiên nằm ở **runtime dependency availability**.
- Ta **chưa cần kết luận** phải sửa annotation, đổi namespace hoặc nâng mọi framework.

### 9.2. Đừng trộn với lỗi compile

Nếu sau đó chạy Maven build trên JDK 17 mà chưa thêm JAXB dependency, sẽ có lỗi kiểu:

```text
package javax.xml.bind does not exist
package javax.xml.bind.annotation does not exist
```

Đó là lỗi **compile classpath**. Trong phép thử chạy nguyên JAR từ Java 8, triệu chứng chủ yếu là **runtime linkage/class loading**. Cùng nguyên nhân dependency, nhưng hai tầng khác nhau; cần ghi tách biệt.

### 9.3. Vì sao --add-modules không giải quyết trên JDK 17?

Từ JDK 11, module `java.xml.bind` đã bị loại bỏ. `--add-modules java.xml.bind` chỉ hữu ích trong các giai đoạn JDK 9/10 có module đó, không có tác dụng hồi sinh module trong JDK 17/21.

## 10. Bước 5 — Nhánh A: giữ javax.xml.bind và thêm dependency tường minh

Đây là cách ít thay đổi source nhất cho một dự án vẫn dùng JAXB 2.x và framework tương thích `javax`.

### 10.1. Chọn đúng thế hệ API và runtime

Một bộ tọa độ minh họa:

| Vai trò | Maven artifact | Version mẫu | Namespace Java |
|---|---|---|---|
| JAXB API | `jakarta.xml.bind:jakarta.xml.bind-api` | `2.3.3` | **`javax.xml.bind.*`** |
| JAXB runtime/provider | `org.glassfish.jaxb:jaxb-runtime` | `2.3.8` | Phục vụ JAXB 2.3/`javax` |
| Activation | Thư viện Activation tương thích mà runtime thực sự yêu cầu | Theo dependency graph | Thường `javax.activation.*` ở thế hệ legacy |

Điểm dễ nhầm là **artifact API có chữ `jakarta` trong tên nhưng version 2.3.3 vẫn chứa `javax.xml.bind`**. Hãy kiểm tra package thật trong JAR nếu công cụ hỗ trợ.

Không kết hợp JAXB API 4.x với source `javax.xml.bind`: API 4.x dùng namespace `jakarta.xml.bind`.

### 10.2. POM cho JDK 17 với API + runtime

Ví dụ POM hoàn chỉnh dùng JDK 17 để biên dịch project hiện tại, **không đổi các import `javax`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
           http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>jaxb-migration-lab</artifactId>
    <version>1.1.0</version>
    <packaging>jar</packaging>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <maven.compiler.release>17</maven.compiler.release>
        <jaxb.api.version>2.3.3</jaxb.api.version>
        <jaxb.runtime.version>2.3.8</jaxb.runtime.version>
        <junit.jupiter.version>5.10.2</junit.jupiter.version>
    </properties>

    <dependencies>
        <!-- API: mã ứng dụng import javax.xml.bind.* -->
        <dependency>
            <groupId>jakarta.xml.bind</groupId>
            <artifactId>jakarta.xml.bind-api</artifactId>
            <version>${jaxb.api.version}</version>
        </dependency>

        <!-- Provider: code JAXB thực thi ở runtime -->
        <dependency>
            <groupId>org.glassfish.jaxb</groupId>
            <artifactId>jaxb-runtime</artifactId>
            <version>${jaxb.runtime.version}</version>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>${junit.jupiter.version}</version>
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
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.jaxb.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Mẫu này dùng các release đã được công bố trước đây để minh họa một nhánh JAXB 2.3. Với dự án production, pin versions theo BOM và support/security matrix hiện hành; không xem các số minh họa là lựa chọn mới nhất hay luôn tối ưu.

Giải thích scope:

- API cần trên **compile classpath** vì source import `JAXBContext` và JAXB annotations.
- API cũng phải khả dụng ở runtime.
- `jaxb-runtime` nằm ở **runtime** vì source trong lab không trực tiếp import class implementation của provider.
- JUnit chỉ dùng trong test.
- Maven thin JAR mặc định **không nhúng** `jaxb-runtime` và các dependency vào file JAR cuối; lệnh chạy phải có classpath hoặc distribution phù hợp.

### 10.3. Build bằng JDK 17

```bash
mvn -version
mvn clean test
```

Nếu JDK 17 là compiler, `maven.compiler.release=17` cho phép source và output ở mức Java 17. Nếu sản phẩm vẫn phải hỗ trợ JDK 8 hoặc 11, chọn release target và dependency versions tương thích tương ứng, rồi kiểm thử trên **minimum runtime JDK** — không tự đặt 17 nếu policy còn hỗ trợ runtime thấp hơn.

### 10.4. Chạy với Maven Exec Plugin

```bash
mvn -q exec:java
```

Goal `exec:java` tạo classpath từ project dependencies theo cấu hình plugin và version. Nó hữu ích cho lab nhưng không phải bằng chứng một thin JAR có thể chạy độc lập bằng `java -jar`.

### 10.5. Kết quả thành công cần được xác minh

- Project compile không cần module JAXB từ JDK.
- `JAXBContext.newInstance(Customer.class)` tạo context.
- Marshal tạo XML có `customer/name/email`.
- Unmarshal phục hồi `Customer`.
- Test dữ liệu tiếng Việt không bị đổi.
- Không còn lỗi `NoClassDefFoundError` hoặc thiếu provider.

Không chỉ dựa vào câu “BUILD SUCCESS”; provider có thể chỉ được tải khi thực thi factory, nên cần test thực sự gọi marshaller/unmarshaller.

## 11. Bước 6 — Viết regression test round-trip

File `src/test/java/com/example/jaxb/JaxbRoundTripTest.java`:

```java
package com.example.jaxb;

import java.io.StringReader;
import java.io.StringWriter;

import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JaxbRoundTripTest {

    @Test
    void shouldMarshalAndUnmarshalVietnameseText() throws Exception {
        Customer original = new Customer(
                "Nguyễn An",
                "an@example.test"
        );

        JAXBContext context = JAXBContext.newInstance(Customer.class);

        Marshaller marshaller = context.createMarshaller();
        StringWriter output = new StringWriter();
        marshaller.marshal(original, output);

        String xml = output.toString();
        assertTrue(xml.contains("<customer"));
        assertTrue(xml.contains("Nguyễn An"));

        Unmarshaller unmarshaller = context.createUnmarshaller();
        Customer restored = (Customer) unmarshaller.unmarshal(
                new StringReader(xml)
        );

        assertEquals("Nguyễn An", restored.getName());
        assertEquals("an@example.test", restored.getEmail());
    }
}
```

Chạy:

```bash
mvn clean test
```

Bài test quan trọng hơn một kiểm tra `Class.forName("javax.xml.bind.JAXBContext")`, vì nó xác minh API **và** provider hoạt động cùng nhau.

### 11.1. Kết quả nên kiểm tra như thế nào?

- Test được test runner phát hiện và thực thi, không bị skip.
- Không có provider lookup exception.
- XML có root, fields và Unicode mong đợi.
- Unmarshal tạo object đúng type và giá trị.
- Source/target compiler levels được in/ghi rõ trong CI.

### 11.2. Kiểm thử XML theo semantics, không phụ thuộc whitespace

Một JAXB provider có thể thêm hoặc bỏ khai báo XML, thay whitespace khi formatted output hoặc khác thứ tự attributes trong XML. Những thay đổi không nhất thiết làm sai XML contract.

Với hợp đồng cần chặt hơn, dùng XMLUnit, schema validation hoặc một parser DOM/XPath và so giá trị/namespace. Chỉ so full string khi format byte-for-byte thật sự là yêu cầu sản phẩm.

## 12. Bước 7 — Giả lập tình huống chỉ có API, thiếu runtime provider

Để hiểu vì sao cần hai dependency, trong **một nhánh lab riêng**, tạm bỏ dependency `jaxb-runtime` khỏi POM rồi chạy lại:

```bash
mvn clean test
```

Có thể xuất hiện `JAXBException` do không tìm thấy implementation/provider, ví dụ exception chain nhắc đến `ContextFactory`, ServiceLoader hoặc thông báo không có JAXB implementation.

Không bảo đảm cùng một thông báo giữa các version/provider. Điều cần xác nhận là:

- Compiler vẫn có API để compile.
- Runtime không thể tạo JAXBContext hoặc marshal/unmarshal.
- Khi khôi phục provider đúng thế hệ, test hoạt động trở lại.

**Đừng giữ thay đổi cố ý gây lỗi trong nhánh chính.** Đây chỉ là negative test để hiểu API/implementation separation.

### 12.1. Vì sao provider có thể bị thiếu dù JAR được khai báo?

Các nguyên nhân có thể gồm:

- Dependency để scope `test`, `provided` hoặc `compileOnly` sai.
- Thin JAR chạy mà không có runtime classpath.
- Fat JAR/shading làm mất `META-INF/services`.
- Application server dùng classloader riêng.
- Provider bị exclusion khi resolve transitive dependencies.
- Version provider không cùng API generation.
- OSGi/JPMS module resolution không phù hợp.

Hãy xem dependency graph và artifact thực tế trước khi thêm nhiều provider để “cho chắc”.

## 13. Bước 8 — Kiểm tra Maven dependency graph

### 13.1. Xem dependency tree

```bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
```

Mục tiêu xác nhận:

- Có JAXB API đúng version.
- Có JAXB runtime/provider.
- Activation dependencies nếu provider cần.
- Không có hai API JAR cùng chứa `javax.xml.bind` ở các version khác nhau.
- Không kéo thêm JAXB 4.x trong nhánh đang dùng `javax`.
- Không có provider vừa cũ vừa mới ngoài chủ đích.
- Tập runtime dependencies được package/launch thật sự cung cấp.

Maven dependency resolution không thể tự phát hiện mọi duplicate classes nằm ở **hai artifact coordinates khác nhau**. Nếu một nhánh dùng cả `javax.xml.bind:jaxb-api` và `jakarta.xml.bind:jakarta.xml.bind-api:2.3.x`, chúng có thể cùng chứa `javax.xml.bind` classes. Hãy chọn một API owner nhất quán.

### 13.2. Effective POM

```bash
mvn help:effective-pom
```

Trong dự án nhiều parent/BOM, version thực tế có thể khác trực tiếp đoạn POM nhìn thấy. Kiểm tra các `dependencyManagement`, Maven profiles và module overrides.

### 13.3. Phân biệt lỗi runtime với lỗi plugin

Nếu JAXB được dùng bởi XJC codegen plugin trong quá trình build, plugin có classpath riêng với application dependencies. Thêm `jaxb-runtime` vào project `<dependencies>` không nhất thiết làm một plugin XJC cũ hoạt động trên Maven JVM mới.

Ngược lại, thêm library vào plugin realm không tự bảo đảm production runtime có JAXB provider.

## 14. Bước 9 — Tổ chức đóng gói khi ứng dụng là thin JAR

### 14.1. Tại sao java -jar có thể vẫn thất bại?

Khi Maven tạo một thin JAR mặc định, file `jaxb-migration-lab-1.1.0.jar` chứa application classes/resources nhưng thường **không chứa mọi dependency JAR**.

Vì vậy:

```bash
java -jar target/jaxb-migration-lab-1.1.0.jar
```

có thể không chạy được vì:

1. Không có `Main-Class` manifest, hoặc
2. Không có `jaxb-api`/`jaxb-runtime` trên runtime classpath.

Không nên kết luận dependency trong POM sai chỉ vì đã chạy sai packaging/launcher.

### 14.2. Các chiến lược phân phối hợp lệ

- Dùng Maven Exec Plugin trong lab.
- Tạo application distribution gồm `bin/` launcher và `lib/` runtime dependencies.
- Dùng framework executable JAR plugin được support.
- Dùng Maven Shade/Assembly hoặc Gradle Shadow khi cần single artifact, đồng thời bảo toàn service metadata.
- Dùng container image copy nguyên app + runtime JARs và classpath rõ.
- Dùng application server cung cấp provider theo contract, với scope phù hợp.

Ví dụ distribution:

```text
jaxb-app/
├── bin/
│   └── launch.sh
├── app/
│   └── jaxb-migration-lab.jar
└── lib/
    ├── jakarta.xml.bind-api-2.3.3.jar
    ├── jaxb-runtime-2.3.8.jar
    └── ...other-runtime-jars...
```

Một launcher POSIX có thể chọn:

```bash
java -cp "app/jaxb-migration-lab.jar:lib/*" \
  com.example.jaxb.App
```

Đường dẫn tương đối chỉ đúng khi working directory phù hợp. Với production, dùng launcher script dựng path dựa trên vị trí của nó và kiểm tra Windows/Linux differences.

### 14.3. ServiceLoader và shaded JAR

JAXB implementations có thể sử dụng provider-discovery metadata. Khi đóng fat JAR, plugin phải xử lý service entries phù hợp nếu nhiều JAR có `META-INF/services`.

Nếu shade bỏ/ghi đè service descriptors, API và provider classes có thể còn trong fat JAR nhưng `JAXBContext.newInstance` vẫn không tìm thấy implementation.

Không relocate `javax.xml.bind` hoặc `jakarta.xml.bind` API packages để “né conflict”: XML binding/framework sẽ tìm binary names chuẩn.

## 15. Bước 10 — Nhánh A với Gradle

Nếu dự án dùng Gradle thay Maven, phân biệt compile API và runtime implementation tương tự.

### 15.1. Groovy DSL (Java application)

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(
        'jakarta.xml.bind:jakarta.xml.bind-api:2.3.3'
    )

    runtimeOnly(
        'org.glassfish.jaxb:jaxb-runtime:2.3.8'
    )

    testImplementation(
        'org.junit.jupiter:junit-jupiter:5.10.2'
    )
}

application {
    mainClass = 'com.example.jaxb.App'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Ví dụ yêu cầu Gradle Wrapper hỗ trợ JDK/toolchain tương ứng; một Gradle bản quá cũ có thể không hiểu `java.toolchain` hoặc không chạy được trên JDK 17. Chọn Wrapper version theo ma trận support của Gradle và plugins.

Chạy trên dự án lab được phép:

```bash
./gradlew --version
./gradlew clean test
./gradlew run
```

Không dùng `compileOnly` cho JAXB API nếu runtime application cần class đó mà không có container khác cung cấp. `runtimeOnly` là lựa chọn phù hợp cho provider khi source không trực tiếp import implementation.

### 15.2. Xem resolved graph

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Kiểm tra runtimeClasspath chứa provider và các hỗ trợ cần thiết; không chỉ nhìn compileClasspath.

### 15.3. application distribution của Gradle

`application` plugin có thể tạo distribution chứa launcher scripts và runtime dependencies theo cấu hình plugin. Với Java CLI nhỏ, đây thường là cách quản lý classpath đơn giản hơn tự tạo một fat JAR.

Tuy nhiên, đừng suy rằng `jar` task mặc định nhúng dependency JARs; cần inspect distribution hoặc dùng script do plugin sinh.

## 16. Bước 11 — Nhánh B: chuyển hẳn sang jakarta.xml.bind

Nhánh A giữ source `javax.xml.bind`. Khi nâng sang stack Jakarta hiện đại, có thể bắt buộc chuyển source/annotations sang `jakarta.xml.bind`.

Đây là **source và binary compatibility migration**, không chỉ thêm runtime dependency.

### 16.1. Thay package import trong model

File `Customer.java` trên nhánh B:

```java
package com.example.jaxb;

import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(name = "customer")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"name", "email"})
public class Customer {
    @XmlElement(required = true)
    private String name;

    @XmlElement(required = true)
    private String email;

    public Customer() {
    }

    public Customer(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }
}
```

### 16.2. Thay import trong App và tests

Trong `App.java` và `JaxbRoundTripTest.java`:

```java
// Nhánh A, JAXB 2.3:
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;

// Nhánh B, JAXB 4.x:
// import jakarta.xml.bind.JAXBContext;
// import jakarta.xml.bind.Marshaller;
// import jakarta.xml.bind.Unmarshaller;
```

Trong code nhánh B thật, **xóa các import `javax` và dùng các import `jakarta`**, không giữ cả hai bộ trong cùng source file vì cùng tên đơn giản và vì chúng không cùng contract.

Các annotation khác cần quét gồm `@XmlElement`, `@XmlAttribute`, `@XmlType`, `@XmlAccessorType`, `@XmlJavaTypeAdapter`, `@XmlSeeAlso`, `package-info.java` và những class do XJC tạo.

### 16.3. API và provider nhánh Jakarta 4.x

Maven dependencies minh họa:

```xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
        <version>4.0.2</version>
    </dependency>

    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>4.0.5</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Chọn những version thực sự tương thích theo Jakarta XML Binding 4.x và dependency management của framework. Các version ở đây là ví dụ về một generation, không phải khuyến nghị version mới nhất cho năm hiện tại.

Trong nhánh B, `jakarta.xml.bind-api` 4.x cung cấp package `jakarta.xml.bind.*`. `jaxb-runtime` 4.x cung cấp provider tương ứng. Các module Activation cần đồng bộ với hệ Jakarta 2.x nếu stack yêu cầu; xem transitive dependency tree thay vì ép cả legacy và new Activation vào cùng runtime.

### 16.4. Gradle tương ứng

```groovy
dependencies {
    implementation(
        'jakarta.xml.bind:jakarta.xml.bind-api:4.0.2'
    )

    runtimeOnly(
        'org.glassfish.jaxb:jaxb-runtime:4.0.5'
    )
}
```

Khi chuyển source sang `jakarta.*`, cập nhật test imports và generated classes. Đừng chỉ nâng versions rồi quên source: compiler sẽ báo `package javax.xml.bind does not exist` nếu API 4.x đã được chọn.

### 16.5. Tại sao không thể chỉ thay JAR?

Hai class khác nhau:

```text
javax.xml.bind.JAXBContext
jakarta.xml.bind.JAXBContext
```

có binary names khác nhau. Bytecode đã compile để gọi `javax.xml.bind.JAXBContext` không tự gọi `jakarta.xml.bind.JAXBContext` khi thay dependency.

Nếu một library/framework cũ vẫn yêu cầu `javax` trong khi ứng dụng chuyển sang `jakarta`, cần nâng library đó hoặc tạo ranh giới adapter tường minh. Không dùng một API JAR 4.x để “thay thế trong suốt” cho API 2.x.

## 17. Quyết định giữ javax hay chuyển jakarta dựa trên framework

| Môi trường mục tiêu | Chiến lược thường phù hợp |
|---|---|
| Java SE CLI/batch cũ, chỉ nâng JDK lên 17/21 | Giữ `javax` + JAXB 2.3 runtime bên ngoài nếu không có yêu cầu khác |
| Ứng dụng Java EE cũ vẫn dùng `javax` | Không đổi namespace JAXB một mình; xem server/runtime ownership |
| Spring Framework 5 / Spring Boot 2 stack cũ | Thường còn các Java EE interfaces hệ `javax`; kiểm tra exact version/support |
| Spring Framework 6 / Spring Boot 3 stack mới | Sử dụng Jakarta APIs ở những integration cần thiết; chọn provider matching generation |
| Jakarta EE 9+ application server | Kiểm tra platform/profile và JAXB version server cung cấp; tránh đóng trùng provider |
| Servlet container thuần | Không mặc định có JAXB runtime; ứng dụng tự cung cấp nếu cần |
| Reusable library hỗ trợ cả hai hệ | Cân nhắc artifacts/adapters riêng, tránh lộ JAXB types không tương thích trong API chung |

Đây là định hướng kiến trúc, không thay ma trận tương thích chi tiết của framework/vendor. Đặc biệt, **nâng JDK** và **nâng Java EE lên Jakarta EE** là hai quyết định khác nhau; có thể thực hiện vào hai phase để giảm rủi ro khi stack cho phép.

## 18. Bước 12 — Kiểm tra dữ liệu XML thật, không chỉ ví dụ Customer

Một ví dụ nhỏ có thể pass nhưng production JAXB models phức tạp hơn:

- Namespace URI, prefix và default namespace.
- `@XmlSchema` trong `package-info.java`.
- `JAXBElement<T>` và `ObjectFactory`.
- `@XmlElementRef`, `@XmlAnyElement` và polymorphism.
- `@XmlAdapter` xử lý date/currency/IDs.
- Attributes bắt buộc, optional elements và null semantics.
- XML Schema validation (XSD).
- Date/time formats, decimals và locale.
- CDATA, escaped characters và Unicode.
- Collections, inheritance, xsi:type.
- Mixed content, comments, unknown elements.
- SOAP headers/attachments nếu tích hợp JAX-WS.

### 18.1. Kiểm thử contract XML

Với dữ liệu nghiệp vụ, bổ sung tests:

1. Marshal object theo model.
2. Parse XML bằng parser đáng tin cậy.
3. So root name, namespaces, element/attribute names.
4. Unmarshal XML fixture từ đối tác hoặc phiên bản cũ.
5. So object values và business invariants.
6. Validate với XSD nếu contract yêu cầu.
7. Chạy negative tests cho XML thiếu/sai field.
8. Kiểm tra encoding và parser security.

Nếu contract thực sự yêu cầu đúng thứ tự elements, `@XmlType(propOrder = ...)` và XSD nên được test. Không chỉ so method getter values mà bỏ qua namespace của XML.

### 18.2. Test tương thích hai chiều khi rolling deployment

Nếu hệ thống có bản cũ và mới chạy cùng lúc:

- Bản JAXB mới có đọc XML do bản cũ ghi không?
- Bản cũ có đọc XML do bản mới ghi không?
- Có thay namespace URI hoặc element names không?
- ObjectFactory/XSD binding output có đổi không?
- Các hệ thống bên ngoài có yêu cầu XML declaration/encoding cụ thể không?

Một migration chỉ thay Java package `javax` → `jakarta` **không bắt buộc đổi XML namespace URI**, nhưng generated code hoặc cấu hình mới có thể làm XML output khác. Phải kiểm chứng trên fixtures và schema, không suy đoán.

## 19. Bước 13 — Bảo đảm encoding UTF-8 khi xuất file

Một nguyên nhân migration bị hiểu nhầm là thay đổi encoding mặc định, đặc biệt trên JDK 18+ khi JEP 400 chuẩn hóa UTF-8 làm default charset cho nhiều Java APIs.

### 19.1. Ví dụ không nên phụ thuộc mặc định

```java
// Charset của hai thao tác phụ thuộc API/default:
byte[] bytes = xml.getBytes();
String decoded = new String(bytes);
```

Những thao tác này có thể khác giữa môi trường, nhất là khi dữ liệu legacy không dùng UTF-8.

### 19.2. Ví dụ đúng khi contract yêu cầu UTF-8

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.Writer;
import javax.xml.bind.Marshaller;

// Tạo marshaller từ JAXBContext có provider hợp lệ.
Marshaller marshaller = context.createMarshaller();
marshaller.setProperty(Marshaller.JAXB_ENCODING, "UTF-8");

Path output = Path.of("customer.xml");

try (Writer writer = Files.newBufferedWriter(
        output, StandardCharsets.UTF_8)) {
    marshaller.marshal(customer, writer);
}
```

Ví dụ sử dụng `Path.of` nên phù hợp với JDK 11+; nếu source phải biên dịch cho Java 8, dùng `Paths.get(...)` thay vì `Path.of(...)`.

**Không** suy rằng đặt `Marshaller.JAXB_ENCODING` đủ để sửa mọi case: nếu đưa một Writer có encoding khác vào marshaller, bytes cuối cùng do Writer xử lý. Với file/network boundary, chọn charset nhất quán theo hợp đồng.

### 19.3. Kiểm thử byte-level

- Kiểm tra bytes được ghi là UTF-8 hợp lệ.
- Đọc lại bằng UTF-8 tường minh.
- Dùng dữ liệu có dấu tiếng Việt.
- Kiểm tra XML declaration tương ứng với encoding thực.
- Test file legacy có encoding khác nếu phải hỗ trợ.
- Không thay dữ liệu đang lưu một cách âm thầm khi nâng JDK.

## 20. Bước 14 — JAXB và bảo mật XML

JAXB thường sử dụng XML parsers ở phía dưới. Nếu dữ liệu XML đến từ nguồn không tin cậy, cần kiểm soát **external entities**, DTD, schema fetching và tài nguyên parser.

### 20.1. Rủi ro XXE

Một XML độc hại có thể tham chiếu external entity hoặc resource:

```xml
<!DOCTYPE customer [
  <!ENTITY ext SYSTEM "file:///some/local/file">
]>
<customer>
    <name>&ext;</name>
    <email>an@example.test</email>
</customer>
```

Ví dụ chỉ minh họa nguy cơ. Không dùng đầu vào độc hại trên máy production để “kiểm tra bằng mắt”; chạy các security tests trong môi trường cô lập.

### 20.2. Thiết kế parser an toàn theo contract

Một hướng là tạo parser StAX với external entities/DTD bị hạn chế rồi truyền reader cho JAXB:

```java
import java.io.StringReader;
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Unmarshaller;
import javax.xml.stream.XMLInputFactory;
import javax.xml.stream.XMLStreamReader;

JAXBContext context = JAXBContext.newInstance(Customer.class);
Unmarshaller unmarshaller = context.createUnmarshaller();

XMLInputFactory factory = XMLInputFactory.newFactory();
factory.setProperty(XMLInputFactory.SUPPORT_DTD, Boolean.FALSE);
factory.setProperty(
        XMLInputFactory.IS_SUPPORTING_EXTERNAL_ENTITIES,
        Boolean.FALSE
);

XMLStreamReader reader = factory.createXMLStreamReader(
        new StringReader(xmlFromUntrustedSource)
);

try {
    Customer customer = (Customer) unmarshaller.unmarshal(reader);
    // Chỉ xử lý customer sau khi các kiểm tra nghiệp vụ đạt.
} finally {
    reader.close();
}
```

Đây là **mẫu thiết kế để thảo luận về parser hardening**, không phải bảo đảm an toàn mọi provider/phiên bản. Cần xác minh XMLInputFactory implementation có hỗ trợ/cưỡng chế các properties, và kiểm soát resolver, external schema access, entity expansion/size/time limits, input length và XSD validation khi cần. Nếu property không được hỗ trợ, không được im lặng bỏ qua mà vẫn cho rằng parser an toàn.

Với SAX/DOM hoặc JAXB APIs nhận `InputStream` trực tiếp, chọn security settings tương ứng theo parser/provider thật. Không chỉ tin rằng nâng JAXB dependency sẽ tự loại bỏ XXE.

### 20.3. XSD validation cũng có rủi ro external access

Khi dùng `SchemaFactory`, có thể cần chặn external DTD/schema fetch theo chính sách, ví dụ với `XMLConstants.ACCESS_EXTERNAL_DTD` và `ACCESS_EXTERNAL_SCHEMA` khi parser hỗ trợ.

Nếu ứng dụng hợp lệ cần import XSD từ đường dẫn nội bộ, cung cấp resolver allowlist có kiểm soát thay vì bật network fetching tùy ý.

## 21. Bước 15 — XJC và schemagen đã không còn được JDK cung cấp

JAXB không chỉ có API/runtime. Nhiều dự án Java 8 dùng các công cụ:

- **XJC:** tạo Java classes từ XSD.
- **schemagen:** tạo XSD từ annotated Java classes.
- **wsimport/wsgen:** thuộc JAX-WS tooling, có thể liên quan SOAP/JAXB models.

Khi nâng lên JDK 11+, các tools từng bundled trong JDK đã bị loại bỏ theo JEP 320. Không chỉ thêm API/runtime rồi giả định lệnh `xjc` hoặc `schemagen` của JDK sẽ trở lại.

### 21.1. Dấu hiệu từ build scripts

Tìm các phần:

```text
xjc
schemagen
wsimport
wsgen
jaxb2-maven-plugin
maven-jaxb2-plugin
jaxb-maven-plugin
xjcGenerate
generateSources
```

Đây là danh sách các tên công cụ/plugin thường gặp; plugin cụ thể có thể khác. Kiểm tra file build và CI scripts thực tế.

### 21.2. Chọn tool riêng cùng generation API

Một quy trình chuẩn:

```text
XSD files
   |
   v
Pinned XJC tool/plugin + matching JAXB generation
   |
   v
Generated Java sources (javax hoặc jakarta)
   |
   v
Java compiler with target release
   |
   v
Application JAR + API/runtime dependencies
```

Nếu source application vẫn `javax`, generated classes phải cùng thế hệ `javax`. Nếu chuyển Jakarta 4.x, codegen tool cũng phải sinh `jakarta.xml.bind.annotation.*`.

Không để generated source của cả hai namespace trong cùng source set ngoài mục đích đã được thiết kế.

### 21.3. Plugin dependency khác application dependency

Maven XJC plugin có **plugin realm** riêng; Gradle XJC task có **configuration** riêng. Cần khai báo generator/tool dependencies và version tại đúng tầng.

Nếu `xjc` của plugin chạy trên Maven JDK mới và fail vì Bytecode/JPMS/removed API, lỗi đó không được sửa chắc chắn bằng cách chỉ thêm `jaxb-runtime` vào application dependencies.

### 21.4. Tái tạo generated source ổn định

Lưu:

- XSD checksums/version.
- XJC version.
- Plugin version và Maven/Gradle Wrapper.
- Java runtime chạy generator.
- Generated package names.
- Source encoding.
- Binding configuration files.
- Namespace migration và customization scripts.
- Diff generated output.

Tránh sửa tay file generated để chạy một lần: khi regenerate trên CI, thay đổi sẽ bị mất hoặc tạo diff khó giải thích.

## 22. Bước 16 — JAXB Activation và các dependency hỗ trợ

### 22.1. Activation là gì?

Một số JAXB/JAX-WS use cases xử lý attachment, MIME hoặc `DataHandler` có thể dùng Activation API/runtime. Trên JDK 8, Activation cũng từng thuộc những API có thể được cung cấp từ JDK; từ JDK 11 đã không còn bundled theo JEP 320.

Khi chuyển dependency:

- Xác định source có import `javax.activation.*` hay `jakarta.activation.*` không.
- Kiểm tra runtime provider có kéo đúng Activation generation không.
- Không đồng thời đóng gói hai API có cùng package/binary names ngoài chủ đích.
- Chạy test attachment/MIME/MTOM nếu hệ thống sử dụng.
- Kiểm tra license, vulnerability và vendor support.

### 22.2. Tại sao không cứ thêm mọi Activation JAR?

Các artifacts khác generation có thể gây duplicate classes hoặc mismatch giữa JAXB API và provider. Một library mang tên `jakarta.activation` phiên bản cũ có thể vẫn chứa namespace `javax.activation`; bản mới dùng `jakarta.activation`.

Dùng Maven/Gradle dependency tree và inspect package thật của JAR. Chọn bộ runtime nhất quán được framework/vendor hỗ trợ, thay vì thêm một loạt JAR chỉ để hết `ClassNotFoundException` trước mắt.

### 22.3. Khi nào cần khai báo Activation trực tiếp?

Nếu application source import trực tiếp Activation types, dependency API tương ứng nên được khai báo tường minh. Nếu chỉ JAXB provider dùng Activation nội bộ, có thể để runtime transitive dependency được quản lý bởi provider/BOM, miễn là artifact cuối thực sự chứa những thư viện cần thiết.

## 23. Bước 17 — Kiểm tra JPMS và module path khi ứng dụng module hóa

### 23.1. Classpath trước, module path sau

Một ứng dụng Java 8 có thể tiếp tục chạy trên classpath dưới JDK 17/21. Nâng JDK không tự bắt buộc tạo `module-info.java`.

Để cô lập JAXB migration, nên làm ứng dụng hoạt động trên classpath trước, sau đó kiểm tra JPMS migration riêng nếu sản phẩm cần modules.

### 23.2. Với named modules

Khi dùng module path, cần:

- Xác định module name thực của JAXB API JAR bằng `jar --describe-module`.
- Khai báo `requires` phù hợp trong `module-info.java`.
- Bảo đảm JAXB provider được resolve.
- Mở package model cho reflection theo nhu cầu của provider.
- Kiểm tra module readability và provider discovery.

Ví dụ ý tưởng cho Jakarta JAXB 4.x:

```java
module com.example.jaxb.app {
    requires jakarta.xml.bind;

    opens com.example.jaxb to jakarta.xml.bind;
}
```

Ví dụ này minh họa mối quan hệ module/API và reflective access; với provider/library thực tế, có thể cần thêm hoặc thay mục tiêu `opens` theo requirements của implementation. Không copy nó cho JAXB 2.3 mà chưa kiểm tra module name của API JAR thực tế.

### 23.3. Tránh dùng --add-opens như giải pháp đầu tiên

Nếu module access fail, xem root cause và module descriptor. Ưu tiên khai báo đúng `opens` của package chứa JAXB model hơn là mở hàng loạt JDK internals với `--add-opens` trong production.

Một lỗi `InaccessibleObjectException` khi provider truy cập fields có thể đến từ model module encapsulation; không nhất thiết là lỗi JDK Java base.

## 24. Bước 18 — Kiểm tra ứng dụng chạy trên server thay vì Java SE

### 24.1. Servlet container không tự bảo đảm JAXB

Một WAR chạy trên servlet container như Tomcat/Jetty có thể cần JAXB API/runtime trong `WEB-INF/lib` nếu ứng dụng sử dụng JAXB và container không cung cấp implementation tương ứng.

Không gán `provided` cho JAXB chỉ vì đó là một “Java EE API”. Scope phải theo **runtime owner thật**.

### 24.2. Jakarta EE application server có thể đã cung cấp JAXB

Một server Jakarta EE đúng profile/version có thể cung cấp JAXB implementation và quản lý provider/classloader. Khi đó ứng dụng có thể compile bằng JAXB API với scope `provided` tùy platform policy; đóng thêm provider của ứng dụng có thể tạo classloader conflict.

Phải kiểm tra:

- Server vendor/version.
- Jakarta EE Platform/Profile capabilities.
- JAXB API generation.
- Provider thực sự được server tích hợp.
- Server classloader policy.
- WAR/EAR packaging contents.
- Trường hợp muốn dùng application-bundled JAXB provider có được vendor hỗ trợ không.

Không đưa nguyên POM dành cho standalone CLI sang full Jakarta EE application server mà bỏ qua owner của runtime.

### 24.3. Spring Boot executable JAR

Một executable JAR do framework đóng gói có runtime classpath riêng. Nếu thêm JAXB dependencies vào Maven/Gradle, phải kiểm tra repackage/bootJar output và test ứng dụng qua launcher thật.

Nếu framework bản mới chuyển từ `javax` sang `jakarta`, JAXB annotations/API phải theo framework support matrix. Không ghép Spring Boot thế hệ Jakarta với các libraries ràng buộc JAXB `javax` rồi mặc định có interoperability.

## 25. Bước 19 — Test JAXB provider qua artifact được triển khai

### 25.1. Test trong Maven chưa bằng test production launcher

`mvn test` có thể chạy vì test classpath chứa dependencies. Nhưng một thin JAR production chỉ có main JAR và thiếu `lib/` vẫn fail khi tạo `JAXBContext`.

Cần test:

1. Compile source.
2. Execute round-trip test trên JDK đích.
3. Package artifact theo mô hình triển khai thật.
4. Liệt kê các runtime dependencies.
5. Launch **chính artifact/distribution sẽ deploy**.
6. Gọi workflow XML/attachment thực.
7. Kiểm tra logs/provider discovery.
8. So sánh output/serialized data với baseline.

### 25.2. Kiểm tra WAR/JAR contents

Ví dụ:

```bash
jar tf target/jaxb-migration-lab-1.1.0.jar
jar tf target/application.war
```

Với WAR, kiểm tra `WEB-INF/lib`. Với executable JAR, kiểm tra nested libraries hoặc manifest/launcher. Với thin JAR, kiểm tra thư mục distribution `lib/`.

Không dùng chỉ `jar tf` main JAR để suy luận về những runtime JAR nằm ngoài nó.

### 25.3. Đừng assert provider implementation class name khi không cần

Có thể in tên provider để chẩn đoán:

```java
JAXBContext context = JAXBContext.newInstance(Customer.class);
System.out.println(context.getClass().getName());
```

Nhưng không nên viết business test phụ thuộc tên implementation class cụ thể trừ khi đó là contract sản phẩm. Tên internal class có thể thay giữa các release provider mà behavior vẫn đúng.

## 26. Bước 20 — Các lỗi phổ biến và root cause

| Triệu chứng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| `package javax.xml.bind does not exist` | Source `javax` nhưng API không trên compile classpath | Maven/Gradle compile dependency |
| `package jakarta.xml.bind does not exist` | Source `jakarta` nhưng API 3/4 không được khai báo | API generation, dependencies |
| `NoClassDefFoundError: javax/xml/bind/JAXBContext` | Runtime JDK 11+ không cung cấp legacy API, artifact thiếu JAR | Runtime classpath/package |
| `NoClassDefFoundError: jakarta/xml/bind/JAXBContext` | Runtime thiếu Jakarta JAXB API | App packaging và runtime graph |
| `JAXBException` không tìm provider | Có API nhưng không có implementation hoặc SPI fail | Runtime provider/service metadata |
| `ClassNotFoundException: ...ContextFactory` | Provider discovery tìm implementation không có/khác version | Provider JAR, API generation |
| `NoSuchMethodError` trong JAXB | Version API/provider/transitive libs xung đột | Dependency graph + loaded class sources |
| `ClassCastException` giữa API types | Hai classloaders hoặc mixed namespace/provider | Server loader và duplicate JARs |
| XJC không chạy sau JDK 11 | Tool từng bundled đã bị loại bỏ | Codegen plugin/tool dependencies |
| Generated code vẫn import `javax` | Generator chưa nâng/đổi target | XJC version, XSD binding |
| JAXBContext tạo được nhưng XML sai namespace | `package-info`, schema hoặc annotation đổi | XML fixtures + XSD |
| Unicode sai dấu | Charset/default I/O khác | Byte-level UTF-8 contract |
| XXE/security warning | Parser chưa được harden hoặc dependency cũ | Secure parser/XSD settings |
| WAR pass tests nhưng fail trên server | Scope/classloader/provider owner khác | Server version + `WEB-INF/lib` |
| Test pass nhưng java -jar fail | Thin JAR không chứa runtime dependencies/manifest | Launcher và packaging |
| `UnsupportedClassVersionError` | Provider hoặc tool compiled cho JDK cao hơn runtime | Class-file major và JDK |
| `InaccessibleObjectException` | JPMS reflective access vào model/package | `module-info`/opens/provider |
| SOAP attachment fail | Activation/JAX-WS stack thiếu hoặc lệch generation | Activation + SOAP runtime |

Đây là gợi ý phân loại, không phải danh sách mapping lỗi–nguyên nhân tuyệt đối. Đọc full stack trace, dependency graph và cách package thực tế trước khi sửa.

## 27. Chẩn đoán lỗi từng bước trong môi trường thật

### 27.1. Phân loại lỗi theo thời điểm

- **Compile:** compiler không tìm package hoặc method.
- **Build code generation:** XJC, schemagen, plugin realm.
- **Application startup:** API/provider/classloader.
- **XML workflow execution:** JAXBContext, marshalling, validation, encoding.
- **Deployment:** WAR/JAR packaging, module path, server-owned providers.
- **Operational:** memory leak, concurrency, performance hoặc native integration.

Đổi Maven dependency là biện pháp khác với sửa một XJC plugin cũ, và đều khác với sửa XML namespace output.

### 27.2. Đọc full exception chain

Ví dụ giả định:

```text
javax.xml.bind.JAXBException:
  Implementation of JAXB-API has not been found
Caused by:
  java.lang.ClassNotFoundException: com.sun.xml.bind.v2.ContextFactory
```

Xác định JAXB API đang dùng version nào, provider nào đáng ra phải có, và classloader nào đang tìm provider. Không mặc định thêm `com.sun.xml.bind` mọi version.

### 27.3. Xác nhận actual class source

Nếu nhiều JAR cùng chứa `javax.xml.bind.JAXBContext` hoặc implementation classes, có thể dùng class-loading logs trên HotSpot khi cần:

```bash
java -Xlog:class+load=info -jar application.jar
```

Với server, logging phụ thuộc runtime và startup configuration. Log có thể rất lớn; chỉ dùng trong điều tra có kiểm soát.

### 27.4. Xác minh API package có trong JAR

Có thể liệt kê:

```bash
jar tf path/to/jakarta.xml.bind-api-2.3.3.jar
```

Nếu là API 2.3, tìm entries dưới `javax/xml/bind/`; nếu API 4.x, tìm `jakarta/xml/bind/`. Không suy luận package từ groupId.

## 28. CI pipeline cho JAXB migration

Một pipeline tham khảo:

```text
Commit / PR
   |
   v
Dependency resolution + lock/BOM verification
   |
   v
Compile (JDK target/toolchain)
   |
   v
JAXB round-trip + schema/contract tests
   |
   v
Generated code/XJC reproducibility check
   |
   v
Package real JAR/WAR/distribution
   |
   v
Runtime smoke on minimum supported JDK
   |
   v
Security/XXE + XML encoding tests
   |
   v
Integration tests with external XML/SOAP contracts
   |
   v
Staging deployment + performance/soak
   |
   v
Release/canary with rollback readiness
```

### 28.1. Tại sao cần kiểm thử trên minimum JDK?

Nếu application target Java 17 nhưng provider/runtime artifact được compile cho Java 21, Maven có thể build thành công trên JDK 21 trong một số cấu hình, trong khi production Java 17 fail.

CI cần kiểm tra:

- Class-file target của application.
- Bytecode level của runtime dependencies.
- Supported minimum JDK của provider.
- JDK chạy tests.
- Artifact cuối đã chứa đúng provider.
- XML/attachments features được gọi thực sự.

### 28.2. Không chỉ chạy test dưới JDK mới nhất

Một dự án công bố hỗ trợ JDK 17 và 21 có thể dùng:

| Stage | JDK | Mục đích |
|---|---|---|
| Compile | JDK phù hợp với toolchain/release target | Tạo bytecode theo policy |
| Unit/integration | 17 | Xác minh minimum supported runtime |
| Unit/integration | 21 | Xác minh target runtime |
| Packaging smoke | 17 và/hoặc 21 theo support | Chạy bản JAR/WAR thực |
| Contract XML | Cùng các runtime được hỗ trợ | So XML/XSD/encoding |
| Production canary | JDK sẽ triển khai | SLO, telemetry, rollback |

Không nhất thiết mọi dự án phải test hai JVM khi policy chỉ hỗ trợ một. Nhưng khi công bố multi-JDK support, test runtime thấp nhất là điều kiện quan trọng.

## 29. Chiến lược phát hành và rollback

### 29.1. Khi chỉ thêm JAXB dependencies ngoài JDK

Nếu source vẫn `javax` và logic XML không đổi, release có phạm vi nhỏ hơn migration Jakarta, nhưng vẫn làm thay đổi:

- Runtime dependency graph.
- Library code/provider version.
- Memory/allocation/performance.
- XML serialization details.
- Packaging và image size.
- Security vulnerabilities/support lifecycle.

Cần so output XML theo contract và chạy canary/staging trên payload thật, không chỉ compile.

### 29.2. Khi chuyển sang Jakarta namespace

Bản mới có bytecode/API khác, có thể ảnh hưởng:

- Public Java API của reusable modules.
- JAX-RS/SOAP/CDI integrations.
- Generated DTOs và annotation processors.
- Framework version compatibility.
- Application server/provider.
- XML namespace/output nếu bindings bị thay.
- Khả năng rollback consumer libraries.

Với nhiều service/library, migration có thể cần release tracks riêng hoặc adapters; không giả định Java modules dùng `javax` và `jakarta` hoán đổi trực tiếp.

### 29.3. Rollback không chỉ là quay về JDK cũ

Nếu bản mới đã ghi XML vào database, message queue hoặc shared filesystem, hãy đảm bảo bản cũ vẫn đọc được dữ liệu đó nếu rollback là yêu cầu. Nếu schema/namespace thay đổi, cần data compatibility hoặc rollback data plan.

Giữ:

- Artifact/checksum baseline.
- Runtime JDK/image cũ được phép.
- Dependency manifest và configuration.
- Migration change log.
- XML contract fixtures.
- Operational metrics và rollback criteria.

Không tắt XML validation hoặc certificate/security checks chỉ để rollback nhanh; những quyết định đó cần risk review riêng.

## 30. Bài tập mở rộng 1 — XML schema và generated DTOs

Giả sử dự án có `src/main/resources/xsd/customer.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           elementFormDefault="qualified">

    <xs:element name="customer">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="name" type="xs:string"/>
                <xs:element name="email" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Bài tập:

1. Sử dụng XJC tool/plugin **bên ngoài JDK** phù hợp với JAXB 2.3 để sinh các class `javax`.
2. Kiểm tra generator không còn gọi `$JAVA_HOME/bin/xjc`.
3. Ghi generated output path và package.
4. Compile/run JAXB round-trip từ generated classes trên JDK 17.
5. Trong nhánh khác, đổi sang XJC tương thích Jakarta 4.x và regenerate.
6. So các generated annotations, ObjectFactory, package-info và XML output.
7. Chứng minh contract XML không thay đổi ngoài chủ đích.

Không cần hardcode plugin version khi mục tiêu là so nhiều toolchains; chọn version được công bố tương thích với JDK, JAXB API generation và framework hiện tại. Kết quả phải được xác minh bằng test trên generated code thật.

## 31. Bài tập mở rộng 2 — Activation và XML attachment

Nếu ứng dụng dùng `DataHandler` hoặc MTOM attachments:

1. Kiểm tra package hiện tại là `javax.activation` hay `jakarta.activation`.
2. Tìm nơi API từng được cung cấp từ JDK/runtime.
3. Chọn Activation API và runtime generation tương thích JAXB/JAX-WS.
4. Kiểm tra transitive dependencies và packaging.
5. Thử payload nhị phân, MIME type và kích thước lớn.
6. Kiểm tra memory usage khi chuyển attachment lớn.
7. So các messages với baseline, bao gồm headers và content-type.

Đừng coi việc marshal một `Customer` có hai trường text là đã kiểm chứng attachment handling.

## 32. Bài tập mở rộng 3 — Trường hợp reusable library

Giả sử library có public method:

```java
public javax.xml.bind.JAXBElement<Customer> exportCustomer(Customer c);
```

Khi chuyển sang:

```java
public jakarta.xml.bind.JAXBElement<Customer> exportCustomer(Customer c);
```

bạn đã thay **public binary signature**. Consumer Java code có thể cần recompile/sửa imports, và các thư viện framework còn dựa vào `javax` sẽ không tự tương thích.

Các hướng thiết kế:

- Duy trì artifact legacy JAXB 2.x và artifact Jakarta 4.x riêng.
- Thay public API để dùng `String`, `byte[]` hoặc domain DTO trung lập với JAXB, nếu contract cho phép.
- Tạo adapter ở boundary, chuyển dữ liệu qua XML/DTO thay vì ép cast giữa hai type systems.
- Công bố support matrix và migration guide cho consumers.
- Kiểm thử binary/source compatibility khi phát hành thư viện.

Đừng chỉ đổi dependency version trong library rồi nói rằng consumer không bị ảnh hưởng.

## 33. Bài tập mở rộng 4 — Một WAR trên servlet container

Một WAR chạy trên servlet container có source `javax.xml.bind`, JDK 17:

1. Xác nhận container có cung cấp JAXB API/provider không.
2. Nếu không, khai báo JAXB 2.3 API và runtime đúng scope để vào `WEB-INF/lib`.
3. Kiểm tra WAR thực tế có API/provider cùng hỗ trợ cần thiết.
4. Deploy lên container version phù hợp.
5. Gọi endpoint marshal/unmarshal XML.
6. Kiểm tra classloading/provider resolution.
7. So output với bản JDK cũ và kiểm tra memory/latency.
8. Trong giai đoạn chuyển sang Jakarta Servlet generation, lập migration plan riêng cho Servlet/JAXB namespace, không đổi từng phần thiếu kiểm soát.

Với Jakarta EE server đầy đủ, server có thể cung cấp JAXB theo profile; khi đó scope/ownership khác với servlet container đơn thuần.

## 34. Các ngộ nhận cần tránh

| Ngộ nhận | Thực tế |
|---|---|
| “JDK 17 vẫn có JAXB vì có `javax.xml.parsers`” | XML parsers của Java SE không đồng nghĩa JAXB API/provider |
| “Thêm `--add-modules java.xml.bind` trên JDK 17 sẽ chạy” | JDK 11+ đã loại bỏ module bundled |
| “JAXB API JAR đủ để marshal XML” | Thường còn cần implementation/provider |
| “JAXB provider đã có qua transitive là không cần kiểm tra” | Transitive graph/package có thể đổi |
| “Mọi artifact có tên jakarta đều chứa package jakarta” | Jakarta XML Binding 2.3.x vẫn có `javax` |
| “Thay API 2.3 bằng 4.x không cần sửa source” | Package/binary names khác |
| “Có JAXB 4.x thì framework javax sẽ dùng được” | Không tự compatible |
| “Maven test pass thì thin JAR chạy độc lập” | Packaging/launcher có thể thiếu runtime libs |
| “Application server nào cũng cung cấp JAXB” | Phụ thuộc server/profile và cấu hình |
| “Servlet container là full Jakarta EE” | Không mặc định cung cấp toàn platform |
| “Đổi JDK là bắt buộc phải regenerate JAXB classes” | Giữ `javax` có thể không cần nếu dependencies phù hợp |
| “XJC sẽ có sẵn trong JDK 21” | XJC/schemagen từng bundled đã bị loại bỏ từ JDK 11 |
| “XML declaration UTF-8 đảm bảo bytes thực là UTF-8” | Output Writer/stream encoding cũng phải đúng |
| “@XmlElement(required=true) tự validate mọi dữ liệu” | Schema validation thường cần cấu hình riêng |
| “Marshaller luôn an toàn với XML không tin cậy” | Unmarshal/parser security cần hardening |
| “Không có JAXB errors khi startup là xong” | Provider có thể chỉ được dùng ở workflow hiếm |
| “Thêm nhiều provider giúp chắc chắn hơn” | Dễ gây SPI/classloader conflicts |
| “Rollback JAR đồng nghĩa rollback dữ liệu” | Dữ liệu XML đã ghi có thể không tương thích |
| “Compile target 17 làm mọi dependency chạy trên Java 17” | Third-party JAR giữ bytecode gốc |

## 35. Hồ sơ bàn giao của bài lab

Sau khi hoàn thành, nhóm nên có:

1. **Baseline JDK:** version, vendor, checksum và cách build/run source cũ.
2. **Target JDK:** version chính xác, JVM flags và runtime ownership.
3. **Namespace decision:** tiếp tục `javax` hay chuyển `jakarta`, với lý do.
4. **Dependency inventory:** JAXB API, runtime, Activation, transitive versions và scopes.
5. **Build artifacts:** POM/Gradle diff, lockfile/BOM, generator/plugin versions.
6. **Generated code:** XJC inputs, plugin version, import namespaces và source target.
7. **Packaging report:** thin/fat JAR, WAR/EAR, providers và `META-INF/services`.
8. **Tests:** round-trip, XSD, Unicode, negative XML, attachment và security.
9. **CI matrix:** compiler JDK, runtime JDK, minimum supported version.
10. **Compatibility report:** XML output và dữ liệu hai chiều với baseline.
11. **Operational risks:** classloader conflicts, perf, XML parse limits, security.
12. **Release plan:** staging, canary, monitoring và rollback data/binary.
13. **Ownership:** người quản lý generated bindings, dependency upgrades và provider support.
14. **Known limitations:** những XML patterns/workflows chưa được thử.

### Mẫu báo cáo bài thực hành

```yaml
lab:
  title: "Externalize JAXB from JDK"
  application: "jaxb-migration-lab"
  baseline:
    java_runtime: "JDK 8"
    JAXB_dependency_source: "Bundled JDK API/runtime"
  target:
    java_runtime: "JDK 17"
    namespace: "javax.xml.bind"
    api: "jakarta.xml.bind-api 2.3.3"
    runtime_provider: "jaxb-runtime 2.3.8"
  tests:
    compile: "PENDING"
    jaxb_context_creation: "PENDING"
    xml_round_trip: "PENDING"
    utf8_round_trip: "PENDING"
    schema_validation: "PENDING"
    packaged_launcher: "PENDING"
  migration_decision:
    path: "Keep javax for this phase"
    next_phase: "Evaluate jakarta 4.x with framework migration"
```

Các trạng thái `PENDING` trong mẫu phải được điền bằng kết quả thực của người thực hành; không xem file bài hướng dẫn là bằng chứng tests đã chạy.

## 36. Checklist hoàn thành

### Dependency và namespace

- [ ] Đã nhận diện dependency ngầm `javax.xml.bind`/JAXB từ JDK cũ.
- [ ] Đã xác nhận JDK 11+ không còn module JAXB bundled.
- [ ] Đã chọn rõ nhánh A `javax` hoặc nhánh B `jakarta`.
- [ ] Đã chọn JAXB API đúng package generation và provider tương thích.
- [ ] Đã tránh duplicate JAXB API JARs chứa cùng binary names.
- [ ] Đã kiểm tra Activation và supporting libraries khi cần.
- [ ] Đã xác minh Maven/Gradle dependency graph đúng scope.

### Source, code generation và build

- [ ] `Customer.java`, `App.java` và tests compile trên JDK mục tiêu.
- [ ] Đã kiểm tra JAXB annotations, `package-info` và ObjectFactory nếu có.
- [ ] Generated source cùng generation namespace.
- [ ] XJC/schemagen không còn phụ thuộc vào tools bundled trong JDK 8.
- [ ] Build plugins và compiler/toolchain versions được pin theo support matrix.
- [ ] Đã thử packaged application, không chỉ source-set tests.

### XML contract và bảo mật

- [ ] Test marshal/unmarshal tạo đúng root, fields, namespace và giá trị.
- [ ] Đã có regression test Unicode tiếng Việt.
- [ ] Đã chỉ định encoding tường minh tại file/network boundary.
- [ ] Đã validate XML/XSD khi business contract yêu cầu.
- [ ] Đã kiểm tra parser settings chống external entities/DTD theo provider.
- [ ] Đã test malformed/empty/missing-field/large XML trong phạm vi cần thiết.
- [ ] Đã kiểm tra attachment/MIME nếu ứng dụng dùng JAX-WS/Activation.
- [ ] Đã test backward/forward XML compatibility khi rolling/rollback cần.

### Runtime và vận hành

- [ ] Runtime có provider JAXB và các transitive libraries.
- [ ] Không dùng `--add-modules java.xml.bind` trên JDK đã bỏ module đó.
- [ ] Đã kiểm tra JPMS/classloader và packaging đúng runtime owner.
- [ ] Đã kiểm tra minimum JDK của các dependency JAR.
- [ ] Đã thử deployment artifact thật trên JDK đích.
- [ ] Đã đối chiếu TLS/I/O/encoding và resource behavior khi liên quan.
- [ ] Đã có checksum, dependency manifest và release notes.
- [ ] Có staging/canary/rollback plan theo mức rủi ro.
- [ ] Chỉ ghi PASS cho các bài kiểm chứng thực sự đã được chạy.

**Kết luận:** Khi rời JDK 8, một dự án dùng JAXB phải chuyển từ tư duy “JDK tự có JAXB” sang **quản lý JAXB như một dependency tường minh có API, implementation/provider, version và scope riêng**. Nếu mục tiêu chỉ là nâng JDK, giữ `javax.xml.bind` với JAXB 2.3 phù hợp có thể là con đường ít rủi ro hơn; nếu đồng thời nâng framework sang Jakarta, phải chuyển cả annotations, generated code, API và runtime sang `jakarta.xml.bind`. Migration được chứng minh thành công không phải ở việc thêm vài dependency vào POM, mà ở **khả năng compile và chạy artifact đã đóng gói trên JDK đích, XML round-trip/contract đúng, codegen tái lập được, parser an toàn và rollback vẫn khả thi**.
