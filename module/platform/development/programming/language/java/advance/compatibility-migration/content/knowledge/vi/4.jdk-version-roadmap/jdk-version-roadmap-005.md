# Nâng cấp JDK 8 lên 11: module, cấu trúc runtime và thành phần bị tách

Nâng cấp từ JDK 8 lên JDK 11 là một bước chuyển lớn vì giữa hai phiên bản có nhiều thay đổi nền tảng được giới thiệu từ Java 9 và tiếp tục hoàn thiện trong Java 10, 11. Những thay đổi này ảnh hưởng đến cách JVM tổ chức runtime, cách ứng dụng truy cập class và package, cách framework sử dụng reflection, cũng như sự hiện diện của các API từng được đóng gói sẵn trong JDK 8.

Ứng dụng Java 8 thông thường vẫn có thể chạy trên JDK 11 nếu bytecode, API, dependency và cấu hình runtime tương thích. Tuy nhiên, việc chỉ thay `JAVA_HOME` rồi khởi động lại ứng dụng là chưa đủ. Cần kiểm kê thành phần, xác định phụ thuộc vào cấu trúc JDK cũ, xử lý các module đã bị tách hoặc loại bỏ, kiểm tra quyền truy cập phản chiếu và xác minh lại toàn bộ đường build, test, triển khai.

## 1. Tổng quan những thay đổi từ JDK 8 đến JDK 11

Java 9 đưa vào Java Platform Module System (JPMS), thay đổi cách tổ chức runtime image và bắt đầu hạn chế truy cập vào một số API nội bộ. Java 10 tiếp tục hoàn thiện nền tảng này. Java 11 loại bỏ một số module Java EE/CORBA từng được phân phối cùng JDK, đồng thời không còn đi kèm JavaFX trong bộ JDK chuẩn.

Các nhóm thay đổi cần khảo sát:

| Nhóm | Thay đổi chính | Tác động thường gặp |
| --- | --- | --- |
| Module system | JPMS, module path, module descriptor, quy tắc readability/exports | Framework hoặc thư viện dùng reflection có thể gặp lỗi truy cập; ứng dụng cần phân biệt classpath và module path. |
| Runtime image | Không còn cấu trúc `rt.jar`, `tools.jar`, `jre/lib/ext` và một số cơ chế boot/extension cũ | Script build, plugin, công cụ đóng gói hoặc ứng dụng tìm class theo đường dẫn JDK 8 có thể hỏng. |
| Java EE và CORBA | Một số module và công cụ được tách khỏi JDK từ Java 11 | Mã gọi JAXB, JAX-WS, Activation, CORBA hoặc JTA có thể không biên dịch/chạy nếu chưa thêm dependency hoặc thay thế. |
| JavaFX | Không còn được đóng gói trong JDK 11 chuẩn | Ứng dụng giao diện JavaFX phải quản lý OpenJFX như dependency/runtime riêng. |
| API nội bộ và reflection | Truy cập nội bộ bị cảnh báo và chịu kiểm soát module; quyền truy cập có thể cần cấu hình tường minh | Có thể gặp cảnh báo, `IllegalAccessError` hoặc `InaccessibleObjectException` tùy kiểu truy cập và cấu hình. |
| Công cụ và tính năng cũ | Một số công cụ/tính năng bị deprecated hoặc thay đổi | Cần lập kế hoạch thay thế, dù không phải tất cả đều bị loại bỏ ngay trong Java 11. |
| Runtime và bảo mật | Có thay đổi về TLS, logging, garbage collection, JFR và các mặc định nền tảng | Cần kiểm thử kết nối, giám sát, hiệu năng và cấu hình vận hành. |

Điểm quan trọng là không phải mọi ứng dụng Java 8 đều cần chuyển sang module hóa hoàn toàn. JDK 11 vẫn hỗ trợ ứng dụng chạy trên classpath. Tuy vậy, ứng dụng cần thích nghi với runtime mới và loại bỏ các giả định phụ thuộc vào cấu trúc JDK 8.

## 2. Java Platform Module System (JPMS)

### 2.1. Vì sao Java có module system?

Trước Java 9, classpath là cơ chế chính để JVM tìm class và resource. Khi classpath lớn, các thư viện có thể vô tình trùng package, thiếu ranh giới phụ thuộc rõ ràng và truy cập quá nhiều chi tiết nội bộ của nhau. Classpath cũng không biểu đạt đầy đủ module nào cần module nào hoặc package nào được công khai.

JPMS bổ sung một lớp tổ chức ở mức module. Một module có thể khai báo:

- Tên module.
- Những module mà nó phụ thuộc thông qua `requires`.
- Những package được công khai cho module khác thông qua `exports`.
- Những package được mở cho reflection thông qua `opens`.
- Những service được cung cấp hoặc sử dụng.

Mục tiêu là làm rõ phụ thuộc và kiểm soát truy cập. Module system cũng cho phép tạo runtime image nhỏ hơn bằng cách chỉ đóng gói những module cần thiết.

### 2.2. Module descriptor `module-info.java`

Một module có tên thường chứa file `module-info.java` ở gốc source set. Ví dụ:

```java
module com.example.orders {
    requires java.sql;
    requires java.logging;

    exports com.example.orders.api;
}
```

Trong ví dụ:

- `module com.example.orders` khai báo tên module.
- `requires java.sql` khai báo phụ thuộc vào module cung cấp JDBC và các API SQL.
- `requires java.logging` khai báo phụ thuộc vào logging API của nền tảng.
- `exports com.example.orders.api` cho phép module khác truy cập các kiểu `public` trong package API này theo quy tắc module.

`exports` không đồng nghĩa với việc mọi package khác trong module đều công khai. Một package không được export vẫn có thể được dùng bên trong module, nhưng module khác không thể truy cập nó như API công khai thông thường.

### 2.3. `exports` và `opens` khác nhau như thế nào?

Hai chỉ thị này giải quyết hai loại truy cập khác nhau:

| Chỉ thị | Mục đích | Trường hợp thường gặp |
| --- | --- | --- |
| `exports` | Công khai các kiểu `public` trong package để module khác truy cập theo quy tắc Java thông thường | Module cung cấp service/API cho module khác. |
| `opens` | Cho phép truy cập phản chiếu sâu (deep reflection) vào package | Framework ORM, dependency injection hoặc serializer cần đọc/ghi field và constructor không công khai. |

Ví dụ mở một package cho một framework cụ thể:

```java
module com.example.orders {
    requires java.sql;

    exports com.example.orders.api;
    opens com.example.orders.entity to org.hibernate.orm.core;
}
```

Chỉ mở đúng package và đúng module cần thiết. Dùng `opens ... to ...` giúp giới hạn phạm vi truy cập hơn so với mở toàn bộ module bằng `open module`.

### 2.4. `requires`, readability và phụ thuộc module

`requires` khai báo rằng module hiện tại cần đọc API công khai của module khác. Có thể gặp:

```java
module com.example.reporting {
    requires com.example.orders;
    requires java.sql;
}
```

Module `com.example.reporting` có thể dùng các kiểu được export bởi `com.example.orders` và API được export bởi `java.sql`. Nếu thiếu quan hệ phụ thuộc cần thiết, quá trình biên dịch hoặc khởi chạy có thể báo lỗi về module không đọc được module khác hoặc package không được export.

Các chỉ thị khác như `requires transitive`, `requires static`, `uses` và `provides` phục vụ những tình huống nâng cao:

- `requires transitive`: truyền khả năng đọc một module phụ thuộc cho module phụ thuộc vào module hiện tại.
- `requires static`: phụ thuộc cần ở thời điểm biên dịch nhưng có thể không bắt buộc ở runtime.
- `uses`: khai báo module sử dụng một service qua `ServiceLoader`.
- `provides ... with ...`: khai báo implementation cung cấp cho một service.

Không cần thêm các chỉ thị này chỉ để chuyển một ứng dụng classpath cũ sang JDK 11. Chỉ dùng khi dự án thực sự được thiết kế thành các named module.

### 2.5. Classpath, module path và unnamed module

JDK 11 tiếp tục hỗ trợ classpath. Khi chạy ứng dụng cũ, có thể dùng:

```bash
java -cp "lib/*;app.jar" com.example.Main
```

Ví dụ trên dùng dấu `;` cho Windows. Trên Linux/macOS, dấu phân tách classpath thường là `:`:

```bash
java -cp "lib/*:app.jar" com.example.Main
```

Các JAR đặt trên classpath thuộc unnamed module. Chúng không cần `module-info.java`, nên đây thường là con đường ít thay đổi nhất cho ứng dụng Java 8 khi bắt đầu chạy trên JDK 11.

Module path dùng để tìm các module có tên hoặc automatic module:

```bash
java --module-path mods -m com.example.orders/com.example.orders.Main
```

Với ứng dụng có module descriptor, JVM phân giải module theo tên và quan hệ phụ thuộc. Một JAR chưa có `module-info.class` nhưng được đặt trên module path có thể trở thành automatic module. Tên automatic module có thể được lấy từ thuộc tính `Automatic-Module-Name` trong manifest hoặc suy ra từ tên JAR.

Không nên chuyển tất cả JAR từ classpath sang module path một cách máy móc. Trước khi làm vậy, hãy kiểm tra tên module, package trùng, split package, quan hệ phụ thuộc và yêu cầu reflection của framework. Một thư viện chạy ổn trên classpath có thể chưa được thiết kế để hoạt động như named module.

### 2.6. Split package và automatic module

Split package xảy ra khi cùng một package được chứa trong nhiều module. Điều này có thể gây lỗi khi các JAR được đặt trên module path vì JPMS yêu cầu ranh giới package rõ ràng hơn.

Ví dụ, hai thư viện cùng chứa class trong package `com.vendor.common`. Trên classpath, kết quả có thể phụ thuộc vào thứ tự tìm kiếm class. Khi chuyển sang module path, việc phân giải module có thể thất bại do package bị chia sẻ giữa nhiều module.

Hướng xử lý thường là:

- Nâng thư viện lên phiên bản đã sửa cách đóng gói.
- Loại bỏ một bản dependency trùng hoặc điều chỉnh dependency graph.
- Chọn một bản thư viện hợp nhất được nhà cung cấp hỗ trợ.
- Tiếp tục dùng classpath cho phần ứng dụng chưa sẵn sàng module hóa.

Automatic module hữu ích như một cầu nối khi đưa thư viện cũ lên module path, nhưng không phải cam kết rằng thư viện đã có thiết kế module ổn định. Nếu thư viện công bố `Automatic-Module-Name`, hãy dùng tên đó thay vì dựa vào tên suy ra từ filename.

### 2.7. Có bắt buộc phải thêm `module-info.java` khi lên JDK 11 không?

Không. Một ứng dụng Java 8 thông thường có thể tiếp tục chạy trên classpath của JDK 11. JPMS là thay đổi quan trọng của nền tảng, nhưng không yêu cầu mọi ứng dụng hiện hữu phải được chuyển thành named module ngay lập tức.

Nên cân nhắc module hóa khi:

- Ứng dụng có ranh giới module rõ ràng và muốn khai báo API công khai.
- Hệ thống cần tạo runtime image tùy chỉnh bằng `jlink`.
- Có kế hoạch phân tách module hoặc cung cấp thư viện cho module khác.
- Muốn kiểm soát chặt phụ thuộc và quyền truy cập package.

Nếu mục tiêu hiện tại chỉ là đưa ứng dụng từ JDK 8 sang JDK 11, trước hết hãy giữ cách đóng gói đang hoạt động, xử lý các thay đổi runtime và dependency, rồi lập kế hoạch module hóa như một công việc riêng khi có lợi ích cụ thể.

## 3. Thay đổi cấu trúc runtime từ JDK 8

### 3.1. Không còn `rt.jar` và `tools.jar`

Trong JDK 8, nhiều class của nền tảng nằm trong `rt.jar`; một số công cụ và API phục vụ phát triển nằm trong `tools.jar`. Một số script, plugin cũ hoặc ứng dụng nội bộ tìm trực tiếp các file này để xác định classpath hoặc gọi compiler.

Từ Java 9, runtime được tổ chức thành các module trong runtime image. JDK 11 không còn cấu trúc JDK 8 với `rt.jar` và `tools.jar`. Vì vậy, các giả định như:

```text
$JAVA_HOME/jre/lib/rt.jar
$JAVA_HOME/lib/tools.jar
```

không còn hợp lệ.

Hãy tìm trong build script, plugin, shell script, Dockerfile và mã nguồn những đoạn:

- Ghép đường dẫn `$JAVA_HOME/lib/tools.jar` vào classpath.
- Đọc class nền tảng từ `rt.jar`.
- Tìm compiler hoặc công cụ JDK bằng cách giả định chúng là một JAR.
- Gọi API nội bộ của `com.sun.tools.*` thay vì API công khai.

Nếu cần gọi compiler từ Java, ưu tiên Java Compiler API (`javax.tools`) hoặc `ToolProvider` trong môi trường JDK phù hợp. Với thao tác build thông thường, gọi Maven/Gradle wrapper hoặc executable JDK theo cách được công cụ hỗ trợ.

### 3.2. Runtime image dạng module

JDK 11 chứa các module nền tảng trong runtime image. Có thể liệt kê module bằng:

```bash
java --list-modules
```

Xem mô tả một module cụ thể:

```bash
java --describe-module java.sql
```

Các công cụ như `jimage` hỗ trợ kiểm tra nội dung runtime image. Không nên viết script phụ thuộc vào đường dẫn nội bộ của runtime image nếu đã có lệnh hoặc API chính thức để truy vấn module.

### 3.3. Không còn extension mechanism cũ

JDK 8 có các cơ chế như extension directory và endorsed standards override. Một số ứng dụng từng đặt JAR trong:

```text
$JAVA_HOME/jre/lib/ext
$JAVA_HOME/jre/lib/endorsed
```

Các cơ chế này không còn được hỗ trợ trong runtime mới. Các system property và tuỳ chọn liên quan như `java.ext.dirs`, `java.endorsed.dirs` và một số cách can thiệp boot class path cũng đã bị loại bỏ hoặc không còn hoạt động như trước.

Nếu ứng dụng dùng extension directory để nạp thư viện, hãy chuyển dependency sang cơ chế quản lý rõ ràng:

- Khai báo dependency trong Maven hoặc Gradle.
- Đóng gói JAR trong thư mục `lib` và đưa vào classpath/module path theo cách triển khai.
- Cấu hình class loader của application server theo hướng dẫn của máy chủ.
- Dùng cơ chế provider hoặc service loading được hỗ trợ nếu thư viện là implementation của một service.

Không sao chép nguyên thư mục `ext` của JDK 8 sang JDK 11 để cố khôi phục hành vi cũ. Việc đó không thay thế được cấu hình classpath hoặc module hợp lệ.

### 3.4. JRE, JDK và runtime image tùy chỉnh

JDK 9 thay đổi cách phân phối runtime image. Không nên giả định JDK luôn chứa thư mục con `jre` theo bố cục cũ, hoặc mọi nhà cung cấp đều phân phối JRE riêng theo cùng một cách.

JDK 11 vẫn có thể được phân phối dưới nhiều hình thức tùy nhà cung cấp: bộ JDK đầy đủ, runtime package hoặc image container. Cần xác nhận sản phẩm nào được hỗ trợ trong môi trường production.

`jlink` cho phép tạo runtime image tùy chỉnh chỉ gồm những module cần thiết:

```bash
jlink \
  --module-path "$JAVA_HOME/jmods" \
  --add-modules java.base,java.sql,java.logging \
  --output custom-runtime
```

Ví dụ trên minh họa việc tạo runtime image chứa các module đã chỉ định. Trên Windows, điều chỉnh dấu nối dòng và biến môi trường theo shell đang dùng. Với ứng dụng thực tế, phải bổ sung tất cả module cần thiết, kể cả module được sử dụng gián tiếp bởi framework, driver, provider hoặc service loading.

`jlink` phù hợp nhất với ứng dụng/module có thể xác định tập module cần thiết. Nếu ứng dụng vẫn chạy trên classpath với nhiều thư viện không module hóa, việc tạo runtime image có thể cần cấu hình thêm hoặc không phải lựa chọn phù hợp cho giai đoạn đầu.

## 4. Các module Java EE và CORBA bị tách khỏi JDK 11

### 4.1. Thay đổi theo JEP 320

JDK 8 từng phân phối một số API Java EE và CORBA cùng bộ JDK. Từ Java 9, các module này đã được đánh dấu deprecated for removal; đến Java 11, chúng bị loại khỏi JDK chuẩn.

Các module đáng chú ý:

| Module bị loại khỏi JDK 11 | API/package thường gặp | Công dụng |
| --- | --- | --- |
| `java.xml.bind` | `javax.xml.bind` (JAXB) | Ánh xạ XML sang object Java và ngược lại. |
| `java.xml.ws` | `javax.xml.ws` (JAX-WS) | Web service SOAP. |
| `java.xml.ws.annotation` | Một số annotation dùng với web service | Annotation hỗ trợ mô tả và xử lý web service. |
| `java.activation` | `javax.activation` | Xác định kiểu dữ liệu và xử lý nội dung activation. |
| `java.corba` | `org.omg.*` | CORBA và Java IDL. |
| `java.transaction` | `javax.transaction` (JTA) | API transaction cho các ứng dụng cần JTA. |
| `java.se.ee` | Module tổng hợp Java EE | Gom các module Java EE liên quan. |

Việc loại bỏ các module này không có nghĩa toàn bộ namespace `javax.*` bị xóa khỏi Java. Nhiều package `javax.*` vẫn thuộc Java SE hoặc được cung cấp bởi thư viện độc lập. Cần xác định đúng package và API ứng dụng đang sử dụng.

Đặc biệt, `javax.transaction.xa` không đồng nhất với API JTA `javax.transaction`. Các API XA cần cho JDBC vẫn được cung cấp qua module `java.sql`; không nên thêm dependency JTA chỉ vì thấy package `javax.transaction.xa` trong mã nguồn.

### 4.2. JAXB: Java Architecture for XML Binding

JAXB thường xuất hiện trong ứng dụng đọc/ghi XML, SOAP hoặc sinh class từ XML schema. Trong JDK 8, ứng dụng có thể dùng các class như:

```java
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
```

Trên JDK 11, JAXB không còn được cung cấp sẵn trong JDK. Nếu ứng dụng cần JAXB, phải khai báo API và implementation tương thích trong dependency của dự án.

Ví dụ dependency Maven theo nhánh JAXB 2.x dùng namespace `javax`:

```xml
<dependencies>
    <dependency>
        <groupId>javax.xml.bind</groupId>
        <artifactId>jaxb-api</artifactId>
        <version>${jaxb.version}</version>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
        <version>${jaxb.version}</version>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Đây là mẫu minh họa; cần chọn phiên bản API và runtime tương thích với nhau, framework đang dùng và chính sách hỗ trợ của dự án. Nếu dùng Maven plugin để sinh class từ XSD, cần kiểm tra riêng phiên bản plugin và cách plugin lấy JAXB implementation.

Không tự động đổi import từ `javax.xml.bind` sang `jakarta.xml.bind` chỉ vì đang nâng JDK 11. Việc chuyển namespace sang `jakarta.*` thuộc lộ trình Jakarta EE tương ứng và có thể đòi hỏi nâng framework, thư viện cũng như mã nguồn ở phạm vi lớn hơn.

### 4.3. JAX-WS và SOAP web service

Các class `javax.xml.ws.*`, công cụ `wsimport` và `wsgen` từng được phân phối trong JDK 8. Trên JDK 11, nếu ứng dụng tạo SOAP client/server hoặc sinh mã từ WSDL, cần bổ sung stack JAX-WS độc lập.

Các việc cần kiểm tra:

- API JAX-WS mà mã nguồn import.
- Runtime implementation, chẳng hạn một implementation như Metro.
- Plugin hoặc công cụ sinh mã từ WSDL.
- JAXB và Activation mà stack SOAP có thể phụ thuộc.
- Cấu hình handler, provider, TLS, chứng thư và serialization.

Không chỉ thêm một API JAR rồi kết luận đã đủ. Ứng dụng cần implementation phù hợp để thực thi SOAP client/server ở runtime.

### 4.4. Java Activation Framework

Activation API thường được dùng gián tiếp bởi JAXB, mail hoặc xử lý MIME. Nếu lỗi xuất hiện ở class `javax.activation.*`, hãy xác định thư viện nào đang cần API này và thêm dependency phù hợp.

Không thêm Activation một cách tùy tiện nếu dependency đã quản lý nó bắc cầu. Trước tiên kiểm tra dependency tree để tránh nhiều phiên bản API hoặc implementation xung đột.

### 4.5. JTA và transaction

Một ứng dụng dùng `javax.transaction.UserTransaction`, `TransactionManager` hoặc annotation liên quan có thể phụ thuộc vào JTA từng được cung cấp bởi JDK 8. Trên JDK 11, cần khai báo API và transaction manager phù hợp với môi trường triển khai.

Phân biệt các trường hợp:

- JDBC local transaction dùng `java.sql.Connection` vẫn thuộc Java SE.
- XA transaction dùng các kiểu trong `javax.transaction.xa` vẫn có API nền tảng qua `java.sql`.
- JTA dùng `javax.transaction` cần API/implementation hoặc transaction manager do application server cung cấp.

Kiểm tra cách ứng dụng được triển khai. Nếu application server cung cấp JTA API, hãy tuân theo hướng dẫn dependency scope của server để tránh đóng gói một bản API xung đột.

### 4.6. CORBA và Java IDL

Các package `org.omg.*` và công cụ liên quan như `idlj`, `orbd`, `servertool`, `tnameserv` không còn nằm trong JDK 11 chuẩn. Nếu ứng dụng dùng CORBA, cần xác định:

- Có thực sự còn gọi CORBA trong runtime hay chỉ còn mã sinh tự động không dùng.
- ORB implementation nào đang được sử dụng.
- Công cụ sinh stub/skeleton và quy trình build thay thế.
- Tương thích giao thức với hệ thống CORBA bên ngoài.

Nếu không còn nghiệp vụ nào dùng CORBA, loại bỏ dependency và mã không cần thiết. Nếu vẫn cần, chọn implementation bên ngoài có hỗ trợ JDK 11 và kiểm thử giao tiếp với hệ thống hiện hữu.

### 4.7. Công cụ Java EE/CORBA đã bị loại bỏ

Ngoài các API runtime, một số công cụ JDK 8 không còn được cung cấp trong JDK 11, ví dụ:

- `wsimport`, `wsgen`: công cụ liên quan JAX-WS.
- `xjc`, `schemagen`: công cụ JAXB/XML schema.
- `idlj`: công cụ CORBA IDL.
- `orbd`, `servertool`, `tnameserv`: công cụ CORBA.

Tìm các lệnh này trong script build, pipeline CI, tài liệu vận hành và máy phát triển. Thay bằng plugin Maven/Gradle hoặc công cụ do implementation tương ứng cung cấp. Không giả định một executable cũ vẫn tồn tại chỉ vì source code không import trực tiếp API đã bị loại.

## 5. JavaFX được tách khỏi JDK

JavaFX không còn được đóng gói trong JDK 11 chuẩn. Ứng dụng desktop JavaFX cần quản lý OpenJFX như dependency và runtime riêng.

Kiểm tra:

- Các import `javafx.*` trong mã nguồn.
- Plugin build và cách tải JavaFX SDK.
- Module JavaFX cần dùng như `javafx.controls`, `javafx.fxml`, `javafx.graphics`.
- Native library theo hệ điều hành/kiến trúc.
- Cách đóng gói và phân phối ứng dụng cho người dùng cuối.

Ví dụ khai báo dependency OpenJFX trong Maven (phiên bản chỉ là biến cấu hình):

```xml
<properties>
    <javafx.version>...</javafx.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-controls</artifactId>
        <version>${javafx.version}</version>
    </dependency>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-fxml</artifactId>
        <version>${javafx.version}</version>
    </dependency>
</dependencies>
```

Chọn phiên bản OpenJFX phù hợp với JDK 11 và plugin đóng gói đang sử dụng. Với ứng dụng có phân phối native, cần kiểm tra classifier theo nền tảng và cách đóng gói runtime; dependency Java thuần không đảm bảo native library đã có trong image.

Lưu ý: tình trạng JavaFX trong JDK 8 phụ thuộc distribution. Một số bộ JDK 8 phổ biến từng đóng gói JavaFX, nhưng không nên coi JavaFX là thành phần luôn có trong mọi bản Java 8.

## 6. Reflection và truy cập API nội bộ

### 6.1. Vì sao framework cũ có thể gặp lỗi?

Framework có thể dùng reflection để truy cập constructor, field hoặc method không công khai. Trước JPMS, nhiều ứng dụng dựa vào việc truy cập sâu vào class của JDK hoặc thư viện khác mà không cần khai báo rõ package được mở.

JPMS đặt ranh giới truy cập giữa các module. Trong JDK 11, cơ chế tương thích `--illegal-access` mặc định vẫn cho phép một số truy cập phản chiếu bất hợp pháp đối với package của JDK tồn tại trong JDK 8, đồng thời phát cảnh báo. Cơ chế này không bảo đảm mọi kiểu truy cập nội bộ đều hoạt động và không nên được xem là giải pháp lâu dài.

Các dấu hiệu cần điều tra:

- Cảnh báo `Illegal reflective access` khi khởi động hoặc chạy test.
- `IllegalAccessError` khi truy cập kiểu hoặc thành viên không được export.
- `InaccessibleObjectException` khi dùng reflection sâu nhưng package chưa được mở.
- Lỗi khởi động framework, ORM, serializer, proxy hoặc dependency injection sau khi đổi JDK.

### 6.2. `--add-exports` và `--add-opens`

Hai tùy chọn này giải quyết hai nhu cầu khác nhau:

| Tùy chọn | Dùng khi | Ví dụ |
| --- | --- | --- |
| `--add-exports` | Cần truy cập các kiểu `public` trong package của module khác vốn không export tới module gọi | `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` |
| `--add-opens` | Framework cần deep reflection vào package của module khác | `--add-opens java.base/java.lang=ALL-UNNAMED` |

`ALL-UNNAMED` chỉ các code thuộc unnamed module, thường là thư viện trên classpath. Nếu code gọi nằm trong named module, chỉ định tên module đó thay vì mở cho tất cả.

Ví dụ cấu hình JVM tạm thời:

```bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar application.jar
```

Trên Windows, điều chỉnh dấu nối dòng. Chỉ thêm package khi stack trace hoặc tài liệu nhà cung cấp xác nhận cần thiết. Không sao chép một danh sách `--add-opens` rộng từ Internet vào mọi môi trường.

### 6.3. Cách xử lý bền vững

Thứ tự ưu tiên khi xử lý cảnh báo hoặc lỗi truy cập:

1. Nâng framework hoặc thư viện lên phiên bản hỗ trợ JDK 11.
2. Dùng API công khai thay cho API nội bộ của JDK.
3. Cập nhật module descriptor bằng `opens` hoặc `exports` đúng phạm vi nếu ứng dụng là named module.
4. Nếu chưa thể nâng thư viện ngay, thêm `--add-opens` hoặc `--add-exports` tối thiểu như giải pháp chuyển tiếp và ghi rõ kế hoạch loại bỏ.

Không nên tắt kiểm soát truy cập hoặc mở toàn bộ module chỉ để làm cho ứng dụng khởi động. Quyền truy cập quá rộng làm giảm khả năng đóng gói và có thể gây thêm vấn đề khi nâng lên các JDK mới hơn.

## 7. Các tính năng và công cụ khác cần lưu ý

### 7.1. Nashorn JavaScript Engine

Nashorn được đánh dấu deprecated từ Java 11. Nó vẫn có mặt trong JDK 11, nhưng ứng dụng không nên coi đây là engine JavaScript có tương lai hỗ trợ dài hạn trong JDK. Nếu hệ thống dùng `ScriptEngineManager` để tìm engine JavaScript, cần xác định engine thực tế được nạp và lập phương án thay thế độc lập nếu cần.

Không nhầm trạng thái deprecated trong Java 11 với việc đã bị loại bỏ ở chính phiên bản này. Việc thay thế nên được lên kế hoạch theo lộ trình JDK tiếp theo và yêu cầu scripting của sản phẩm.

### 7.2. Pack200

Pack200 và Unpack200 được đánh dấu deprecated từ Java 11. Nếu pipeline phân phối JAR hoặc quy trình cập nhật đang dùng `pack200`/`unpack200`, hãy tìm cách thay thế và kiểm tra công cụ đóng gói của hệ thống. Tính năng này bị loại bỏ ở các JDK sau đó, nên không nên xây dựng quy trình mới dựa trên nó.

### 7.3. TLS 1.3 và thay đổi bảo mật

JDK 11 bổ sung triển khai TLS 1.3. Khi nâng JDK, cần kiểm tra kết nối đến server, proxy, database và dịch vụ bên ngoài, đặc biệt khi hệ thống có cấu hình protocol/cipher suite cố định hoặc sử dụng security provider riêng.

Kiểm thử:

- Handshake TLS đến các endpoint thực tế.
- Truststore, keystore, certificate chain và hostname verification.
- Cipher suite và protocol mà server/client cùng hỗ trợ.
- JDBC, LDAP, SMTP, SOAP hoặc HTTP client có TLS.

Không tự hạ mức bảo mật chỉ để khắc phục lỗi kết nối. Trước tiên xác định protocol/cipher không tương thích và điều chỉnh theo chính sách bảo mật của tổ chức.

### 7.4. Unified JVM Logging và Java Flight Recorder

Java 9 giới thiệu unified JVM logging, thay đổi cách cấu hình nhiều log nội bộ của JVM. Những script dùng các cờ logging cũ cần được đối chiếu với cú pháp `-Xlog`.

Java Flight Recorder (JFR) được đưa vào OpenJDK và có thể dùng để quan sát hoạt động JVM, hiệu năng và sự kiện runtime. Nếu hệ thống có quy trình profiling hoặc giám sát, kiểm tra khả năng tích hợp của agent và công cụ phân tích đang sử dụng.

### 7.5. Garbage collector và hiệu năng

G1 trở thành garbage collector mặc định từ Java 9. Ứng dụng Java 8 có thể đang chạy Parallel GC hoặc cấu hình collector khác. Khi chuyển sang JDK 11, hãy ghi nhận collector thực tế trước và sau migration, rồi đo:

- Thời gian pause và tần suất GC.
- Throughput, latency và CPU.
- Heap occupancy, allocation rate và memory pressure.
- Hành vi khi tải cao và khi ứng dụng khởi động lại.

Không kết luận hiệu năng tốt hơn hoặc kém hơn chỉ dựa trên tên collector. Chạy workload đại diện và so sánh số liệu trong điều kiện tương đương.

## 8. Kiểm kê dấu vết phụ thuộc vào JDK 8

Trước khi thay JDK, tìm các dấu vết trong repository và môi trường triển khai:

| Dấu vết | Vị trí cần tìm | Hướng xử lý |
| --- | --- | --- |
| `rt.jar`, `tools.jar` | Script, plugin build, classpath, mã gọi compiler | Dùng công cụ/API được hỗ trợ; bỏ giả định đường dẫn JDK 8. |
| `jre/lib/ext`, `java.ext.dirs` | Script cài đặt, biến môi trường, cấu hình máy chủ | Khai báo dependency và classpath/module path rõ ràng. |
| `java.endorsed.dirs` | JVM options, startup script | Nâng thư viện và dùng cơ chế dependency/provider hiện hành. |
| `-Xbootclasspath/p` | Startup options, test runner | Loại bỏ cách prepend boot classpath; tìm API mở rộng được hỗ trợ. |
| `javax.xml.bind`, `javax.xml.ws`, `javax.activation` | Import, reflection, dependency tree, generated source | Thêm API/implementation độc lập hoặc thay stack tương ứng. |
| `javax.transaction` | Import, application server config, dependency | Xác định JTA provider và scope dependency. |
| `org.omg.*`, `idlj`, `orbd` | Source, generated source, build scripts | Loại bỏ hoặc chọn CORBA implementation ngoài JDK. |
| `javafx.*` | Source, build file, packaging | Thêm OpenJFX và runtime/native components phù hợp. |
| `sun.*`, `com.sun.*` | Source, dependency và log | Thay API nội bộ bằng API công khai; nâng thư viện. |
| `setAccessible(true)` | Reflection code và framework integration | Kiểm tra module access, cập nhật framework, mở package có giới hạn. |
| `pack200`, `unpack200` | Release/package scripts | Thay quy trình nén/đóng gói. |
| Nashorn/JavaScript engine | `ScriptEngineManager`, script resources | Đánh giá engine độc lập và lộ trình thay thế. |

Có thể dùng tìm kiếm văn bản trong repository để định vị nhanh. Ví dụ với `rg`:

```bash
rg -n "rt\.jar|tools\.jar|java\.ext\.dirs|java\.endorsed\.dirs|Xbootclasspath|javax\.xml\.bind|javax\.xml\.ws|javax\.activation|javax\.transaction|org\.omg|javafx\.|pack200|unpack200" .
```

Đây chỉ là bước sàng lọc. Mã sinh tự động, dependency bắc cầu, cấu hình được tải từ bên ngoài và tên class được nạp động có thể không xuất hiện trong tìm kiếm source thông thường.

## 9. Quy trình migration đề xuất từ JDK 8 lên JDK 11

### Bước 1: Chụp lại baseline JDK 8

Ghi nhận:

- JDK distribution, phiên bản và vendor.
- JVM options, GC, heap, system properties và security configuration.
- Phiên bản Maven/Gradle wrapper, plugin, CI runner và application server.
- Dependency tree và artifact hiện tại.
- Build log, unit/integration test, startup log và số liệu hiệu năng.

Chạy build/test trên môi trường JDK 8 hiện tại để có mốc so sánh. Lưu cả cách triển khai thực tế, không chỉ lệnh chạy trong máy lập trình viên.

### Bước 2: Kiểm tra khả năng hỗ trợ JDK 11 của công cụ

Đối chiếu phiên bản Maven/Gradle, compiler plugin, test plugin, code generator, application server, container base image, agent và driver với tài liệu của nhà cung cấp. Nâng công cụ build lên phiên bản hỗ trợ chạy trên JDK 11 trước hoặc theo một nhánh thay đổi riêng.

Phân biệt JDK chạy build với target release. Một build có thể chạy bằng JDK 11 nhưng tạo bytecode Java 8 trong giai đoạn chuyển tiếp nếu dự án vẫn cần hỗ trợ runtime Java 8. Nếu mục tiêu sản phẩm là bỏ Java 8, hãy thống nhất target release và supported minimum trước khi sửa cấu hình.

### Bước 3: Kiểm kê API và module đã bị tách

Tìm các package Java EE/CORBA, JavaFX, API nội bộ và các giả định về cấu trúc JDK 8. Kiểm tra dependency tree để phát hiện thư viện dùng JAXB, JAX-WS, Activation hoặc JTA gián tiếp.

Phân loại từng phát hiện:

- Còn sử dụng trong runtime production.
- Chỉ dùng ở build-time hoặc code generation.
- Chỉ dùng trong test.
- Không còn được sử dụng và có thể loại bỏ.
- Chưa rõ, cần truy vết thêm.

### Bước 4: Cập nhật dependency và công cụ bị ảnh hưởng

Thêm API và implementation đã tách khỏi JDK vào dependency management, hoặc nâng framework lên phiên bản tự quản lý các thành phần này. Thay công cụ sinh mã đã bị loại bỏ bằng plugin/tooling được hỗ trợ. Cập nhật JavaFX, CORBA hoặc scripting engine nếu ứng dụng thực sự cần.

Chọn các phiên bản tương thích với nhau và với JDK 11. Tránh thêm nhiều implementation cùng lúc hoặc đóng gói API mà application server đã cung cấp.

### Bước 5: Chạy trên JDK 11 và xử lý lỗi module/reflection

Chuyển môi trường build/test sang JDK 11, chạy clean build và ghi lại lỗi đầu tiên theo từng nhóm:

- Không tìm thấy class/package đã bị tách.
- Compiler hoặc plugin không tương thích JDK 11.
- Lỗi module access hoặc illegal reflective access.
- Lỗi bytecode, class loading hoặc dependency conflict.
- Lỗi TLS, provider, native library hoặc runtime configuration.

Nâng framework/thư viện trước khi thêm các cờ mở quyền truy cập. Nếu cần `--add-opens` hoặc `--add-exports`, ghi lại package, module đích, lý do và kế hoạch loại bỏ.

### Bước 6: Kiểm thử chức năng và vận hành

Chạy unit test, integration test, end-to-end test và các luồng nghiệp vụ trọng yếu. Kiểm tra các chức năng XML/SOAP, transaction, desktop UI, CORBA hoặc scripting nếu hệ thống có sử dụng.

Kiểm tra triển khai trên container/server thực tế, agent, TLS, logging, GC, monitoring, shutdown và khả năng khôi phục. So sánh hiệu năng với baseline JDK 8 trong điều kiện tương đương.

### Bước 7: Chuẩn hóa và phát hành

Sau khi ứng dụng hoạt động ổn định, chuẩn hóa:

- Build JDK và compile release.
- Runtime image/container image.
- JVM options và cấu hình bảo mật.
- Dependency lock/version management.
- Hướng dẫn phát triển, kiểm thử và triển khai.
- Ma trận JDK được hỗ trợ và phương án rollback.

Nếu vẫn cần hỗ trợ Java 8 trong một giai đoạn, duy trì build/test matrix riêng. Không công bố hỗ trợ Java 8 chỉ vì artifact có bytecode target 8; tất cả dependency và runtime profile cũng phải đáp ứng yêu cầu đó.

## 10. Công cụ hỗ trợ khảo sát JDK 11

### 10.1. Liệt kê module nền tảng

```bash
java --list-modules
```

Lệnh này giúp xác nhận module có trong runtime đang chạy. Nếu một module Java EE/CORBA không xuất hiện, cần xác định ứng dụng có phụ thuộc vào nó hay không và bổ sung implementation bên ngoài nếu cần.

### 10.2. Phát hiện phụ thuộc API nội bộ

```bash
jdeps --recursive --jdk-internals path/to/application.jar
```

Kết quả giúp định vị một số tham chiếu tới API nội bộ của JDK. Kiểm tra thêm các dependency JAR và các class được nạp động; phân tích một artifact đơn lẻ không bao phủ toàn bộ runtime.

### 10.3. Xem module của một JAR

```bash
jar --describe-module --file path/to/library.jar
```

Lệnh giúp xác định JAR có module descriptor, automatic module hoặc thông tin module nào. Nếu thư viện không được thiết kế để dùng trên module path, tiếp tục dùng classpath có thể phù hợp hơn.

### 10.4. Kiểm tra API deprecated

```bash
jdeprscan --release 11 path/to/application.jar
```

Lệnh hỗ trợ phát hiện tham chiếu tới một số API deprecated trong artifact. Cần đọc kết quả cùng tài liệu migration và kiểm thử; không phải mọi cảnh báo đều đồng nghĩa ứng dụng hỏng ngay trên JDK 11.

## 11. Tiêu chí hoàn thành migration JDK 8 lên 11

- [ ] Build tool, plugin, CI runner và application server hỗ trợ JDK 11.
- [ ] Đã loại bỏ giả định về `rt.jar`, `tools.jar`, extension directory và endorsed standards override.
- [ ] Đã xác định ứng dụng tiếp tục dùng classpath hay có kế hoạch module hóa; không chuyển module path máy móc.
- [ ] Đã xử lý các dependency JAXB, JAX-WS, Activation, JTA hoặc CORBA bị tách khỏi JDK nếu ứng dụng cần chúng.
- [ ] Đã tách JavaFX thành dependency/runtime riêng nếu ứng dụng dùng JavaFX.
- [ ] Đã kiểm tra API nội bộ và cảnh báo reflection; các cờ `--add-opens`/`--add-exports` còn lại có lý do và phạm vi rõ ràng.
- [ ] Đã rà soát Nashorn, Pack200, TLS, logging, GC và các công cụ vận hành có liên quan.
- [ ] Build sạch và bộ kiểm thử cần thiết chạy thành công trên JDK 11.
- [ ] Các luồng nghiệp vụ, kết nối ngoài, bảo mật và triển khai được xác minh trong môi trường gần production.
- [ ] Có số liệu so sánh với baseline, phương án rollback và tài liệu supported JDK được cập nhật.

Hoàn tất các bước này giúp migration JDK 8 lên 11 có thể được đánh giá bằng bằng chứng. Nếu ứng dụng chưa cần module hóa, tiếp tục dùng classpath là lựa chọn hợp lệ trong giai đoạn chuyển đổi. Điều cần bảo đảm là mọi API và công cụ từng được JDK 8 cung cấp đều đã được xác định, dependency được quản lý tường minh và runtime JDK 11 đã được kiểm thử trên đúng cấu hình triển khai.
