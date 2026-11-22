# Log4j bridge — kết nối facade và backend trong Java

## 1. Vấn đề mà Log4j bridge giải quyết

Một ứng dụng Java hiếm khi chỉ có một logging API. Mã do nhóm phát triển viết có thể gọi **Log4j API**; thư viện bên thứ ba có thể gọi **SLF4J API**; thư viện JDK hoặc module cũ có thể dùng **java.util.logging (JUL)**; một số phụ thuộc khác gọi **Apache Commons Logging (JCL)** hoặc API **Log4j 1.x**. Nếu mỗi nguồn chọn một cơ chế ghi khác nhau, sự kiện sẽ phân tán ra console, file, backend hoặc định dạng khác nhau, gây khó khăn khi tìm kiếm, cảnh báo và điều tra.

**Logging bridge** là thành phần chuyển lời gọi logging từ **API nguồn** sang **API đích**. Bridge giúp ứng dụng giữ nguyên source code của thư viện cũ nhưng vẫn đưa các sự kiện về một hệ thống xử lý chung.

Ví dụ khi **Log4j Core** được chọn làm backend:

~~~text
Mã ứng dụng dùng Log4j API -----------+
                                      |
Thư viện dùng SLF4J --[SLF4J bridge]--+---> Log4j API ---> Log4j Core
                                      |                        |
Module dùng JUL -------[JUL bridge]---+                        +--> LoggerConfig
                                      |                        +--> Filter
Thư viện dùng JCL ------[JCL bridge]--+                        +--> Appender
                                                               |
                                                               v
                                                       stdout / file / collector
~~~

**Cốt lõi:** Bridge có **chiều**. Muốn đưa SLF4J vào Log4j Core là một hướng; muốn đưa Log4j API sang SLF4J/Logback là hướng ngược lại. Nếu cài cả hai chiều, có thể tạo vòng lặp và làm logging không hoạt động.

Sau bài học, bạn có thể:

- Phân biệt logging facade, API, backend, binding/provider, bridge và Appender.
- Xác định hướng của các artifact **log4j-slf4j2-impl**, **log4j-slf4j-impl**, **log4j-to-slf4j**, **log4j-jul**, **log4j-to-jul**.
- Hiểu cách bridge các nguồn JUL, JCL, JPL và Log4j 1.x.
- Chọn dependency dựa trên backend cuối cùng, không dựa trên tên artifact có chữ Log4j.
- Cài bridge SLF4J 2 và JUL tới Log4j Core bằng Maven, biên dịch chương trình Java target 17 và kiểm chứng stdout.
- Phân tích nguy cơ vòng lặp bridge, provider xung đột, log trùng, log mất, lệch level, mất context và tác động hiệu năng.

**Phạm vi:** Bài thuộc phần *Facade và backend* của *Java Core Logging*. Trọng tâm là đường đi của logging events và kiến trúc kết nối API, không phải hướng dẫn viết Appender hoặc một logging framework mới.

## 2. Phân biệt các lớp của hệ thống logging

| Khái niệm | Chức năng | Ví dụ |
| --- | --- | --- |
| **Logging API** | Hợp đồng để mã Java phát logging request | Log4j API, SLF4J, JUL, JCL |
| **Facade** | API ổn định để mã gọi không gắn chặt vào backend | SLF4J thường được gọi là facade |
| **Implementation/backend** | Áp dụng cấu hình, xử lý và xuất sự kiện | Log4j Core, Logback, JUL |
| **Bridge/adapter** | Chuyển sự kiện/lời gọi từ API này sang API khác | SLF4J → Log4j API, JUL → Log4j API |
| **Binding/provider** | Implementation của một API được chọn khi chạy, có thể là bridge | log4j-slf4j2-impl cung cấp SLF4J 2 provider |
| **Appender/Handler** | Đưa event tới đích ghi | Log4j Console Appender, JUL FileHandler |
| **Layout/encoder** | Chuyển event thành text/JSON/byte | PatternLayout, JSON Template Layout |

**Một bridge không tự trở thành backend có Appender đầy đủ.** Chẳng hạn, **log4j-slf4j2-impl** có nhiệm vụ nhận lời gọi của SLF4J 2 API và chuyển sang Log4j API. Còn **log4j-core** là implementation đọc cấu hình Log4j2 và ghi qua Appender.

Có thể nhìn thành hai giai đoạn:

~~~text
Compile-time API                 Runtime bridge/provider       Backend
---------------------------------------------------------------------------
Log4j API ---------------------------------------------------> Log4j Core
SLF4J API ----------------------> log4j-slf4j2-impl ----------> Log4j Core
JUL API ------------------------> log4j-jul ------------------> Log4j Core
~~~

Đây là mô hình khi đích cuối là Log4j Core. Nếu đích cuối thay bằng Logback, bridge cần được đảo chiều theo thiết kế.

### 2.1. Tại sao không cần sửa code của thư viện?

Ví dụ thư viện đã biên dịch dùng SLF4J:

~~~java
org.slf4j.Logger logger =
        org.slf4j.LoggerFactory.getLogger("library.orders");
logger.info("event=order.created id={}", "ORD-42");
~~~

Đây là mảnh code nằm trong một phương thức và cần dependency SLF4J; nó không có main nên không chạy độc lập. Khi runtime có provider SLF4J phù hợp hướng tới Log4j API, thư viện vẫn gọi **org.slf4j.Logger** như trước, nhưng sự kiện được xử lý bởi Log4j Core.

**Bridge khác source migration.** Nếu bạn thay toàn bộ org.slf4j.Logger bằng org.apache.logging.log4j.Logger, đó là di chuyển API trong mã nguồn. Bridge giữ API nguồn và đổi đường thực thi phía sau, rất hữu ích với dependency ngoài.

### 2.2. Có phải cài càng nhiều bridge càng tốt?

Không. Chỉ thêm bridge cho API thực tế xuất hiện và cần chuyển về backend đã chọn. Thêm một bridge không dùng gây tăng độ phức tạp; thêm bridge ngược chiều có thể tạo vòng lặp.

Cách ra quyết định:
1. Xác định **API nguồn** của từng module/thư viện.
2. Chọn **một backend đích** cho ứng dụng.
3. Vẽ một đường mũi tên từ mỗi API đến backend.
4. Kiểm tra không có mũi tên quay ngược về API nguồn.

## 3. Ma trận bridge của Log4j 2

| API nguồn | API/backend đích | Artifact | Lưu ý quan trọng |
| --- | --- | --- | --- |
| Log4j API | Log4j Core | **log4j-api + log4j-core** | Đường xử lý gốc, không cần bridge |
| SLF4J **2.x** | Log4j API | **log4j-slf4j2-impl** | SLF4J 2 provider |
| SLF4J **1.7.x** | Log4j API | **log4j-slf4j-impl** | Không thay bằng bản dành cho SLF4J 2 |
| JUL | Log4j API | **log4j-jul** | Thay LogManager sớm hoặc dùng Log4jBridgeHandler |
| JCL | Log4j API | **log4j-jcl** / cơ chế JCL tương thích | Cần kiểm tra JCL version và classpath |
| Log4j 1.x API | Log4j 2 API | **log4j-1.2-api** | Cầu nối tương thích cho migration, có giới hạn |
| JPL / System.Logger | Log4j API | **log4j-jpl** | Khác JUL; phụ thuộc cơ chế LoggerFinder |
| Log4j API | SLF4J API | **log4j-to-slf4j** | CHIỀU NGƯỢC với log4j-slf4j2-impl |
| Log4j API | JUL | **log4j-to-jul** | CHIỀU NGƯỢC với log4j-jul |

Hai cặp tên đặc biệt dễ nhầm:

**log4j-slf4j2-impl**: nhận SLF4J 2 và đưa **vào Log4j API**.  
**log4j-to-slf4j**: nhận Log4j API và đưa **sang SLF4J API**.

**log4j-jul**: đưa JUL **vào Log4j API**.  
**log4j-to-jul**: đưa Log4j API **sang JUL**.

**Không chọn chiều bằng cảm giác từ tên file JAR.** Kiểm tra bảng chức năng của artifact và vẽ đường event thực tế trước khi khai báo dependency.

## 4. Hướng A: nhiều API → Log4j Core

Giả sử ứng dụng chọn Log4j Core làm backend trung tâm:

~~~text
App code (Log4j API) -----------------+
                                      |
Library A (SLF4J 2) ---> provider ----+---> Log4j API ---> Log4j Core
                                      |                         |
Library B (JUL) --------> bridge -----+                         +--> Console
                                      |                         +--> RollingFile
Library C (JCL) --------> bridge -----+                         +--> Collector
~~~

Khi đó:
- Code dùng Log4j API cần **log4j-api**.
- Ứng dụng cần **log4j-core** và một cấu hình LoggerConfig/Appender phù hợp.
- Thư viện dùng SLF4J 2 cần provider **log4j-slf4j2-impl**.
- Nếu cần gom JUL, dùng **log4j-jul** và chọn cách khởi động thích hợp.
- Với JCL/Log4j 1.x, chỉ cài bridge tương thích khi thật sự cần.

Điểm lợi là nhiều nguồn log có thể dùng cùng **level policy**, **format**, **routing**, **retention** và **collector** thông qua backend trung tâm. Tuy nhiên, bridge không tự đảm bảo tất cả record đã được lưu: Filter, Appender, async queue và hệ lưu trữ vẫn có thể loại/bỏ event.

### 4.1. SLF4J 2 → Log4j2

Dependency logic:

~~~text
slf4j-api 2.x              API cho code/thư viện gọi SLF4J
log4j-slf4j2-impl          provider SLF4J 2 -> Log4j API
log4j-api                  API đích
log4j-core                 backend/implementation
~~~

Khi code dùng SLF4J gọi:

~~~java
org.slf4j.Logger slf4j =
        org.slf4j.LoggerFactory.getLogger("billing.service");
slf4j.info("event=payment.retry attempt={}", 2);
~~~

sự kiện có thể được Log4j Core nhận như các event từ Log4j API, với Logger name, level, message và dữ liệu liên quan được chuyển theo hợp đồng bridge.

### 4.2. SLF4J 1.7 khác SLF4J 2.x

SLF4J 2.x sử dụng cơ chế provider khác với SLF4J 1.7.x. Do đó:

- **SLF4J 1.7.x hoặc cũ hơn:** **log4j-slf4j-impl**.
- **SLF4J 2.x:** **log4j-slf4j2-impl**.

Không tráo hai artifact chỉ vì cùng có chữ slf4j. Nếu classpath chứa nhiều version của **slf4j-api**, cần xử lý dependency conflict; đừng phán đoán từ version khai báo trực tiếp trong pom mà bỏ qua transitive dependencies.

### 4.3. Chỉ một SLF4J provider tương thích

Không nên mang cả **logback-classic** và **log4j-slf4j2-impl** với ý định “dự phòng”. Chúng đều có thể cung cấp logging implementation/provider cho SLF4J. Một runtime cần một lựa chọn rõ ràng; nhiều provider có thể tạo cảnh báo và hành vi không mong muốn.

Để xem dependency tree:

~~~bash
mvn dependency:tree
~~~

Lệnh này áp dụng trong dự án Maven có pom.xml. Xác minh provider được chọn **ở runtime**, nhất là khi một framework/starter đưa dependency vào gián tiếp.

## 5. Hướng B: Log4j API → SLF4J/Logback

Nếu ứng dụng đã chọn **Logback** làm backend, nhưng một thư viện sử dụng Log4j API, đường phù hợp có thể là:

~~~text
Library (Log4j API)
        |
        v
    log4j-to-slf4j
        |
        v
      SLF4J API
        |
        v
     Logback backend
~~~

**log4j-to-slf4j** đi từ Log4j API sang SLF4J. Trong hệ này **không được cài log4j-slf4j2-impl** để đưa SLF4J ngược lại Log4j API.

Tương tự, nếu backend đích là JUL mà code dùng Log4j API, module **log4j-to-jul** đi theo chiều Log4j API → JUL. Nó **không** giúp JUL vào Log4j Core.

### 5.1. Một ứng dụng không nhất thiết phải chuyển toàn bộ mã nguồn

Bridge tồn tại để các thư viện tiếp tục dùng API chúng đã chọn. Nếu đội phát triển muốn đổi Logging API trong source, có thể migrate có kế hoạch; tuy nhiên, **đổi backend** và **đổi API** là hai công việc khác nhau. Việc đổi backend không nhất thiết kéo theo sửa hàng nghìn câu LOG.info trong business code.

## 6. Cấm vòng lặp bridge

Sai lầm nghiêm trọng nhất:

~~~text
SLF4J API
   |
   | log4j-slf4j2-impl
   v
Log4j API
   |
   | log4j-to-slf4j
   v
SLF4J API
   |
   +--------> quay lại đầu
~~~

**Không cài log4j-slf4j2-impl và log4j-to-slf4j cùng nhau.** Hai cầu nối ngược chiều có thể dẫn đến vòng logging, xung đột provider, lỗi khởi tạo hoặc logging ngừng hoạt động. Với SLF4J 1.x cũng không kết hợp **log4j-slf4j-impl** với **log4j-to-slf4j**.

Các cảnh báo kiến trúc khác:

- Cài provider SLF4J hướng Log4j cùng provider hướng Logback gây lựa chọn backend không rõ.
- Dùng JUL → SLF4J → Log4j API có thể hợp lệ về hướng nhưng dài hơn JUL → Log4j API trực tiếp.
- Cài nhiều JUL Handler cùng xuất một event tới một backend có thể nhân đôi log.
- Gắn cùng Console Appender ở LoggerConfig con và Root với additivity không mong muốn có thể nhân đôi record, dù bridge đúng.
- Một event đi qua nhiều lớp chuyển đổi có thể có thay đổi ngữ nghĩa context/level; phải kiểm chứng chứ không giả định hoàn toàn tương đương.

**Quy tắc:** mỗi API nguồn chỉ cần một đường có chủ đích tới backend cuối. Đường nào quay lại chính nguồn hoặc có hai tuyến tới cùng đích đều phải được đánh giá trước khi deploy.

## 7. JUL → Log4j2: đặc điểm riêng của Java Util Logging

Một thư viện phát log bằng:

~~~java
java.util.logging.Logger jul =
        java.util.logging.Logger.getLogger("legacy.payment");
jul.info("event=legacy.ready");
~~~

đang dùng **JUL**, logging API tích hợp trong JDK. Thêm **log4j-core** vào classpath **không tự chuyển** JUL sang Log4j2. Module **log4j-jul** hỗ trợ hai cách quan trọng.

### 7.1. Thay JUL LogManager lúc JVM khởi động

Đặt JVM system property:

~~~text
java.util.logging.manager=org.apache.logging.log4j.jul.LogManager
~~~

Ví dụ về hình thức tham số:

~~~bash
java -Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager -cp "..." Main
~~~

Lệnh này chỉ minh họa: classpath và class Main phải được thay bằng ứng dụng thực; lệnh chạy đầy đủ ở mục 10.

**Đặt property trước khi JUL được khởi tạo.** Vì JUL LogManager nằm trong hạ tầng logging chung của JVM, một thư viện có thể gọi JUL từ giai đoạn bootstrap, trước main(). Đặt **System.setProperty** quá muộn không bảo đảm thay thế được manager đã được khởi tạo.

Cách thay LogManager có thể hiệu quả hơn Handler bridge bởi các JUL logging calls được đưa vào Log4j API mà không phải chạy hết pipeline JUL tiêu chuẩn rồi mới chuyển tiếp.

**Giới hạn:** Tài liệu Log4j lưu ý JUL **Handler** không được hỗ trợ theo cùng cách trong cơ chế thay LogManager này; những ứng dụng dựa trên custom JUL Handlers cần đánh giá khả năng tương thích. Không tùy tiện dùng property này trong application server nơi nhiều ứng dụng cùng chia sẻ hạ tầng JUL.

### 7.2. Sử dụng Log4jBridgeHandler

Nếu môi trường đã khởi tạo JUL trước khi ứng dụng có thể đặt system property, **org.apache.logging.log4j.jul.Log4jBridgeHandler** là lựa chọn khác. Nó là một JUL Handler có nhiệm vụ chuyển LogRecord sang Log4j.

~~~text
JUL Logger
    |
    v
JUL Handler: Log4jBridgeHandler
    |
    v
Log4j API --> Log4j Core --> Appender
~~~

Ví dụ trong file **logging.properties** của JUL:

~~~properties
handlers = org.apache.logging.log4j.jul.Log4jBridgeHandler
~~~

Đây chỉ là **đoạn cấu hình**; cần bảo đảm Handler được nạp từ log4j-jul, backend Log4j Core hoạt động và các JUL level phù hợp. Log4j cũng hỗ trợ cài Handler bằng API **Log4jBridgeHandler.install()**.

**Rủi ro:** nếu còn JUL ConsoleHandler cũ song song với bridge Handler, một record có thể được ghi ở cả hai đích. Bởi record đi qua pipeline JUL rồi Log4j, Handler bridge có thể tốn chi phí hơn cách thay LogManager. Log4j có tùy chọn **propagateLevels** để giảm xử lý event bị tắt theo cấu hình backend, nhưng phải kiểm thử level mapping.

### 7.3. Nên chọn cách nào?

| Điều kiện | Hướng cân nhắc |
| --- | --- |
| Chủ động JVM startup, muốn tích hợp trực tiếp | LogManager replacement trong log4j-jul |
| JUL đã khởi tạo sớm, không thay được manager | Log4jBridgeHandler |
| Cần giữ nhiều custom JUL Handlers | Kiểm thử đường Handler bridge và lifecycle |
| Không có nguồn JUL cần gom | Không cần cài log4j-jul |
| Hệ thống yêu cầu audit bền vững | Thiết kế delivery/retention riêng, không chỉ bridge |

**Lưu ý:** Spring Boot hoặc container có thể đã tích hợp bridge, nên phải xác minh cấu hình thực tế trước khi cài thêm.

## 8. JCL, JPL và Log4j 1.x

### 8.1. JCL / Apache Commons Logging

JCL dùng API **org.apache.commons.logging**. Trong kiến trúc lấy Log4j2 làm backend, **log4j-jcl** là một phương án chuyển JCL về Log4j API khi tương thích với version Commons Logging/loader đang sử dụng.

Một số ứng dụng đi đường JCL → SLF4J → Log4j2; đường này có thể hợp lệ nếu các mũi tên đều một chiều, nhưng phải hiểu rằng có nhiều tầng chuyển hơn. Không cài đồng thời nhiều implementation của JCL mà không xác định thứ tự class loading/provider.

### 8.2. JPL / System.Logger

**System.Logger** (Java Platform Logging) khác **java.util.logging.Logger** dù cùng là các API gắn với JDK. Log4j có cơ chế **log4j-jpl** để tích hợp System.Logger với Log4j API. Cần kiểm tra **System.LoggerFinder**, thời điểm provider được chọn và tính tương thích runtime; không suy luận rằng **log4j-jul** tự bridge tất cả các lời gọi JPL trong mọi môi trường.

### 8.3. Log4j 1.x API

Legacy code có thể dùng:

~~~java
import org.apache.log4j.Logger;
~~~

Log4j 2 API sử dụng package khác:

~~~java
import org.apache.logging.log4j.Logger;
~~~

**log4j-1.2-api** là lớp tương thích giúp nhiều lời gọi API Log4j 1.x đi vào hệ Log4j2 trong giai đoạn migration. Tuy nhiên **không có nghĩa mọi appender, cấu hình và extension Log4j 1.x sẽ được tái hiện 100%**. Cần xem hướng dẫn migration và kiểm thử integration.

Không xem module tương thích là lý do giữ implementation legacy lỗi thời vô thời hạn. Rà soát dependencies, chính sách bảo mật và lộ trình chuyển mã nguồn khi phù hợp.

## 9. Quản lý phiên bản và dependencies

Một hệ đang sử dụng Log4j Core thường cần các artifact Log4j đồng bộ phiên bản. **log4j-bom** là phương án quản lý version thống nhất cho **log4j-api**, **log4j-core**, **log4j-slf4j2-impl**, **log4j-jul** và các module khác.

**Trách nhiệm của library:** thư viện Java dùng chung thông thường chỉ cần phụ thuộc logging API; ứng dụng tiêu thụ quyết định implementation. Việc đưa sẵn Logback/Log4j Core hay provider vào thư viện khiến các ứng dụng khác dễ bị xung đột.

**Trách nhiệm của application:** chọn backend cuối, khai báo runtime providers/bridges cần thiết, cấu hình LoggerConfig/Appender và kiểm thử.

Dùng Maven để xem graph:

~~~bash
mvn dependency:tree
~~~

Tìm cả direct và transitive artifacts:
- slf4j-api, logback-classic;
- log4j-api, log4j-core;
- log4j-slf4j2-impl, log4j-slf4j-impl, log4j-to-slf4j;
- log4j-jul, log4j-to-jul, jul-to-slf4j;
- log4j-jcl, jcl-over-slf4j;
- log4j-1.2-api và implementation cũ còn tồn tại.

Nếu tìm thấy hai bridge ngược chiều hoặc hai provider SLF4J, cần loại lựa chọn không phù hợp. **Mục tiêu không phải classpath có ít JAR nhất**, mà là mỗi API có một đường đi rõ ràng tới backend đã chọn.

## 10. Ví dụ chạy độc lập: Java 17 + Maven, ba API cùng tới Log4j2

Bài demo sử dụng **Log4j 2.26.1**, **SLF4J 2.0.17**, Maven compiler target **Java 17**. Các phiên bản này được chọn cố định để bài có thể tái lập, không phải tuyên bố rằng mọi dự án phải dùng đúng các version đó. Trước khi dùng production, cập nhật theo phiên bản và khuyến cáo bảo mật hiện hành.

Mục tiêu:
1. Phát một event qua **Log4j API**.
2. Phát một event qua **SLF4J 2 API**.
3. Phát một event qua **JUL**.
4. Cả ba được Log4j Core in với **cùng PatternLayout**.
5. In ra tên JUL LogManager để xác nhận bridge được khởi tạo đúng lúc.

### 10.1. Cấu trúc dự án

~~~text
log4j-bridge-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── bridge/
        │           └── BridgeDemo.java
        └── resources/
            └── log4j2.xml
~~~

### 10.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId><artifactId>log4j-bridge-demo</artifactId><version>1.0</version>
  <properties><maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding></properties>
  <dependencyManagement><dependencies><dependency>
    <groupId>org.apache.logging.log4j</groupId><artifactId>log4j-bom</artifactId>
    <version>2.26.1</version><type>pom</type><scope>import</scope>
  </dependency></dependencies></dependencyManagement>
  <dependencies>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-api</artifactId></dependency>
    <dependency><groupId>org.slf4j</groupId><artifactId>slf4j-api</artifactId><version>2.0.17</version></dependency>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-core</artifactId><scope>runtime</scope></dependency>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-slf4j2-impl</artifactId><scope>runtime</scope></dependency>
    <dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-jul</artifactId><scope>runtime</scope></dependency>
  </dependencies>
  <build><plugins><plugin><groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId><version>3.14.0</version>
    <configuration><release>17</release></configuration>
  </plugin></plugins></build>
</project>
~~~

**Vì sao phân scope như vậy?** Source dùng trực tiếp Log4j API và SLF4J API nên chúng có mặt ở compile. Các artifact **log4j-core**, **log4j-slf4j2-impl**, **log4j-jul** phục vụ runtime trong demo. BOM đảm bảo các module Log4j thống nhất phiên bản.

Không thêm **log4j-to-slf4j** vào pom.xml này: nó sẽ tạo chiều quay ngược từ Log4j API về SLF4J.

### 10.3. src/main/resources/log4j2.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration>
  <Appenders>
    <Console name="CONSOLE" target="SYSTEM_OUT">
      <PatternLayout pattern="%level|%logger|%msg%n"/>
    </Console>
  </Appenders>
  <Loggers>
    <Logger name="demo.bridge" level="INFO" additivity="false">
      <AppenderRef ref="CONSOLE"/>
    </Logger>
    <Root level="ERROR"><AppenderRef ref="CONSOLE"/></Root>
  </Loggers>
</Configuration>
~~~

Các Logger có tên thuộc **demo.bridge** được cấu hình INFO và dùng một Console Appender ghi stdout. **additivity=false** giúp tránh cùng event bị chuyển thêm tới Root Appender. Root ERROR làm cấu hình nền cho những Logger khác.

**Bridge chỉ quyết định đường event.** PatternLayout, level, Filter và Appender do Log4j Core quản lý.

### 10.4. src/main/java/demo/bridge/BridgeDemo.java

~~~java
package demo.bridge;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.slf4j.LoggerFactory;

public final class BridgeDemo {
    private static final Logger LOG4J = LogManager.getLogger("demo.bridge.app");
    private static final org.slf4j.Logger SLF4J =
            LoggerFactory.getLogger("demo.bridge.lib");
    private static final java.util.logging.Logger JUL =
            java.util.logging.Logger.getLogger("demo.bridge.jul");

    public static void main(String[] args) {
        LOG4J.info("source=log4j event=ready");
        SLF4J.info("source=slf4j event=order.created id={}", "ORD-42");
        JUL.info("source=jul event=legacy.ready");
        System.out.println("jul-manager="
                + java.util.logging.LogManager.getLogManager().getClass().getName());
    }
}
~~~

Chương trình dùng đúng ba API, không chứa một custom bridge. Các dependency và JVM property điều khiển cách định tuyến. Dòng cuối giúp xác nhận JUL LogManager thực sự là class do log4j-jul cung cấp.

### 10.5. Build project và chạy một JVM riêng

Đứng tại thư mục chứa pom.xml, chạy:

~~~bash
mvn -q -B package dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

Sau đó **chạy java trực tiếp bằng JVM mới**, với JUL system property đặt **trước khi khởi tạo JUL**.

Trên **Linux/macOS**:

~~~bash
java -Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager \
  -cp "target/classes:$(cat classpath.txt)" demo.bridge.BridgeDemo
~~~

Trên **Windows PowerShell**:

~~~powershell
$deps = (Get-Content .\classpath.txt -Raw).Trim()
java '-Djava.util.logging.manager=org.apache.logging.log4j.jul.LogManager' -cp "target\classes;$deps" demo.bridge.BridgeDemo
~~~

**Phân biệt classpath separator:** Unix thường dùng **:**, Windows dùng **;**. Trong môi trường Maven nhiều plugin, đừng giả định chạy **exec:java** ngay bên trong JVM của Maven sẽ luôn đủ sớm để thay JUL LogManager; lệnh trên tạo JVM riêng và đặt property khi startup.

### 10.6. stdout đã kiểm chứng

Chương trình đã được **biên dịch với target Java 17 và thực thi** với các dependency/version kể trên. Dưới đây là stdout của nó:

~~~text
INFO|demo.bridge.app|source=log4j event=ready
INFO|demo.bridge.lib|source=slf4j event=order.created id=ORD-42
INFO|demo.bridge.jul|source=jul event=legacy.ready
jul-manager=org.apache.logging.log4j.jul.LogManager
~~~

**Dòng 1:** Log4j API đi trực tiếp tới Log4j Core.  
**Dòng 2:** SLF4J 2 API đi qua log4j-slf4j2-impl, tham số {} được thay bằng ORD-42.  
**Dòng 3:** JUL được log4j-jul chuyển vào Log4j API vì manager đã được thay lúc JVM khởi động.  
**Dòng 4:** Xác nhận LogManager của JUL đúng là org.apache.logging.log4j.jul.LogManager.

Các dòng có **cùng format**, không xuất thêm JUL ConsoleHandler mặc định và không lặp qua Root Appender. Vì thế chúng minh họa được một pipeline tập trung có thể kiểm chứng.

### 10.7. Nếu bỏ bridge thì sao?

| Thay đổi | Điều cần dự đoán và kiểm tra |
| --- | --- |
| Bỏ log4j-slf4j2-impl | SLF4J thiếu provider mong đợi hoặc chọn provider khác |
| Bỏ log4j-jul hoặc JVM property | JUL trở về LogManager/Handler khác và có thể in định dạng khác |
| Bỏ log4j-core | Không còn backend Log4j Core/Appender đã cấu hình |
| Thêm log4j-to-slf4j | Xung đột chiều định tuyến với SLF4J → Log4j API |
| Đổi LoggerConfig level sang WARN | Các event INFO của demo có thể bị loại theo Log4j Core |
| Bật additivity=true | Event có thể được chuyển tới Root Appender và gây trùng |

Không nên cố tình đưa vòng bridge vào hệ production để “thử nghiệm”; hãy kiểm tra dependency graph và chọn một hướng trước.

## 11. Level mapping, context và dữ liệu qua bridge

Bridge chuyển event nhưng các API không có tập khái niệm hoàn toàn giống nhau.

### 11.1. Level mapping

| Mục đích | SLF4J | Log4j2 | JUL |
| --- | --- | --- | --- |
| Rất chi tiết | TRACE | TRACE | FINEST/FINER tùy bridge |
| Chẩn đoán | DEBUG | DEBUG | FINE |
| Thông tin | INFO | INFO | INFO |
| Cảnh báo | WARN | WARN | WARNING |
| Lỗi | ERROR | ERROR | SEVERE |

Đây là bảng định hướng, **không phải mapping tuyệt đối cho mọi phiên bản**. Log4j2 có FATAL; JUL có CONFIG và nhiều mức FINE. Adapter thực tế có thể có quy tắc chuyển cụ thể.

Một record JUL **FINE** có thể bị JUL Logger/Handler lọc **trước khi** vào Log4j Core, ngay cả khi LoggerConfig đích bật DEBUG. Với Handler bridge, cần kiểm tra cả level JUL và level Log4j2. Tránh vội tăng tất cả lên ALL nếu chưa biết event bị chặn ở đâu.

### 11.2. MDC và ThreadContext

SLF4J dùng **MDC**; Log4j2 có **ThreadContext**. Provider/bridge tương thích có thể đưa context vào Log4j Core; nhưng không mặc định mọi kiểu dữ liệu hoặc context được bảo toàn 100% qua mọi chuỗi bridge.

Khi cần requestId/traceId:
- Kiểm tra output sau Layout/Encoder, không chỉ xem MDC.put có chạy.
- Dùng scope try/finally hoặc API hỗ trợ đóng context.
- Truyền context có kiểm soát qua ExecutorService, CompletableFuture và async processing.
- Không dùng ThreadLocal của request này cho request khác khi thread pool tái sử dụng.
- Không ghi password, token, cookie hoặc dữ liệu riêng tư vào MDC/ThreadContext.

### 11.3. Marker, Throwable và caller location

Một logging API có thể hỗ trợ Marker, structured Message, key-value pairs hoặc Throwable theo cách khác API đích. Bridge có thể ánh xạ nhưng không bảo đảm mọi metadata được bảo toàn giống hệt.

Hãy kiểm thử:
1. Throwable và nguyên nhân lỗi có đi tới Appender?
2. Stack trace có được format đúng?
3. Marker cần để filter có được giữ và hiển thị?
4. Caller class/method/source location có còn là vị trí business code hay đã trở thành lớp adapter?
5. Khi async, event được chụp context ở thời điểm nào?

Nếu downstream dựa vào dữ liệu có cấu trúc, dùng schema ổn định và encoder đúng; đừng chỉ parse lại message text rồi cho rằng bridge đã chuyển đủ mọi field.

## 12. Những vấn đề vận hành cần lưu ý

### 12.1. Hiệu năng

Bridge có thể tăng chi phí chuyển event, ánh xạ level/metadata và định dạng. Với JUL BridgeHandler, event đi qua JUL trước khi vào Log4j Core nên có chi phí thêm so với LogManager replacement.

Đo hiệu năng theo workload thực tế: throughput, CPU, latency, allocations và tình huống sink chậm. Một cấu hình async có thể giảm tác động lên request nhưng vẫn có nguy cơ queue đầy, block/drop và mất record khi JVM dừng đột ngột.

### 12.2. Log trùng

Hai nguyên nhân thường gặp:
- **Hai đường routing** từ một nguồn: JUL ConsoleHandler cùng BridgeHandler hoặc hai provider/backend được cấu hình không rõ.
- **Additivity/Appender** trong Log4j Core: LoggerConfig con và Root cùng ghi một event về đích chung.

Cách sửa không phải xóa hết Handler hoặc đặt additivity=false cho mọi Logger. Cần vẽ đúng tuyến, xác định những đích cần thiết và kiểm chứng số record cuối cùng.

### 12.3. Bảo mật và dữ liệu nhạy cảm

Bridge không tự động làm sạch mọi message. Nếu thư viện đã ghi token, password, cookie, private key, credential hoặc toàn bộ payload nhạy cảm, việc gom về một backend tập trung có thể làm dữ liệu đó lan rộng hơn.

Giảm thiểu dữ liệu **ngay tại nguồn**, dùng escaping/JSON encoder đúng, thiết lập quyền truy cập, retention và redaction tại các lớp phù hợp. Log ở DEBUG cũng không mặc nhiên an toàn vì DEBUG có thể được bật khi điều tra.

### 12.4. Logging API của thư viện và implementation của ứng dụng

Thư viện Java dùng chung thường chỉ nên phụ thuộc **logging API**; lựa chọn backend cuối thuộc ứng dụng. Thư viện không nên ép runtime của ứng dụng có một provider cụ thể, vì có thể xung đột với framework hoặc ứng dụng khác.

Ứng dụng cuối cùng cần kiểm soát dependency graph, chọn một backend, cài bridge cho API thực sự tồn tại và kiểm thử trước khi deploy.

## 13. Tình huống chẩn đoán thường gặp

| Triệu chứng | Điểm cần xem | Hướng sửa |
| --- | --- | --- |
| SLF4J không xuất qua Log4j Core | SLF4J 2 provider có hiện diện? | Dùng log4j-slf4j2-impl phù hợp |
| Runtime có nhiều SLF4J providers | logback-classic và Log4j provider cùng xuất hiện? | Chọn một provider/backend |
| Có lỗi về log4j-to-slf4j | Bridge ngược chiều cùng được cài? | Bỏ vòng SLF4J ↔ Log4j |
| JUL vẫn xuất ra stderr của JDK | java.util.logging.manager được đặt sớm chưa? | Đặt ở JVM startup hoặc dùng Handler bridge |
| JUL FINE không xuất | Level tại JUL và Log4j2 | Xem cả hai lớp lọc |
| Một event xuất hai lần | JUL Handler cũ hoặc Log4j additivity | Loại đường routing thừa |
| Layout không giống giữa API | Nguồn log đi qua hai backend | Xác minh provider và pipeline |
| requestId mất khi qua thread | Context propagation | Truyền/snapshot context và dọn scope |
| Marker/Throwable không có ở output | Adapter/Encoder/PatternLayout | Kiểm thử ngữ nghĩa từng field |
| Tăng mạnh log volume sau bridge | Gom thêm nguồn hoặc phát trùng | Điều chỉnh level, routing, retention |
| Appender ghi file lỗi | Quyền ghi/path/queue/backpressure | Kiểm tra sink, không chỉ bridge |
| Source import Log4j 1.x không chạy với Log4j2 | Thiếu module tương thích hoặc API không tương thích | Đánh giá log4j-1.2-api và migration |

**Trình tự điều tra:** API nguồn → bridge/provider → Log4j API → LoggerConfig/Filter → Appender/Layout → output. Nếu không chứng minh được bước nào đang hoạt động, đừng đoán chỉ dựa trên việc thiếu một dòng console.

## 14. Checklist triển khai an toàn

Trước khi đưa cấu hình bridge vào một ứng dụng thật, kiểm tra:

- **Một backend cuối** đã được lựa chọn và được cấu hình rõ ràng.
- Các **API nguồn** đã được kiểm kê từ source và dependency tree.
- Mỗi bridge có **chiều đúng**, không có vòng lặp.
- SLF4J version và provider artifact **tương thích**.
- Các module Log4j2 dùng **version đồng bộ** (BOM khi phù hợp).
- JUL LogManager replacement, nếu được chọn, được cấu hình **trước khi JUL khởi tạo**.
- JUL Handler bridge, nếu được chọn, không giữ Handler dư gây duplicate.
- Log event từ từng API đến cùng backend với **đúng level, Logger name và layout**.
- Marker, context, Throwable và location đã được test nếu ứng dụng dựa vào chúng.
- Async/backpressure, quyền ghi, shutdown, error handling và retention đã có phương án phù hợp.
- Không có dữ liệu bí mật hoặc log injection trong output.
- Có thể rollback/loại bridge khi integration thất bại.

**Không đoán số lượng log mong đợi từ một cấu hình trừu tượng.** Tạo test event với key/Logger name phân biệt, quan sát đầu ra thật và đánh giá liệu có mất hay nhân đôi record.

## 15. Bài thực hành

**Bài 1 — Chọn bridge đúng chiều:** Một thư viện dùng SLF4J 2, ứng dụng muốn Log4j Core. Chọn artifact nào?  
Gợi ý: **log4j-slf4j2-impl**, không phải log4j-to-slf4j.

**Bài 2 — Chọn backend Logback:** Ứng dụng dùng SLF4J/Logback, có thư viện dùng Log4j API. Vẽ đường đi và chọn artifact cho Log4j API.  
Gợi ý: **Log4j API → log4j-to-slf4j → SLF4J → Logback**.

**Bài 3 — Sự cố JUL startup:** Trong một application server JUL đã được khởi tạo trước khi ứng dụng deploy. Không thể thay manager. Có cách nào chuyển JUL vào Log4j Core?  
Gợi ý: **Log4jBridgeHandler**, sau đó kiểm tra Handler cũ và overhead.

**Bài 4 — Kiểm tra level:** Trong demo, đổi LoggerConfig demo.bridge thành **WARN**. Dự đoán vì sao các bản ghi INFO không còn xuất qua Log4j Core dù API nguồn vẫn gọi info().

**Bài 5 — Duplicate:** Thêm một JUL ConsoleHandler song song với cầu JUL, hoặc bật additivity=true trong ví dụ Log4j Core. Quan sát vì sao một sự kiện có thể xuất nhiều dòng. Không làm điều này trong production.

**Bài 6 — Chẩn đoán dependency graph:** Pom có log4j-slf4j2-impl, log4j-to-slf4j và logback-classic. Backend cuối muốn là Log4j Core. Hãy xác định các dependency cần loại và giải thích tại sao.

**Bài 7 — Structured logging:** Gắn requestId qua MDC trong module dùng SLF4J, rồi dùng Log4j2 Layout hiển thị. Kiểm chứng scope và không rò context khi thread pool tái sử dụng.

**Bài 8 — Migration legacy:** Module import org.apache.log4j.Logger. Tìm hiểu log4j-1.2-api, liệt kê các cách sử dụng cũ cần kiểm thử thêm: custom appender, cấu hình, caller location, MDC/filters.

## 16. Câu hỏi tự đánh giá

**1. Bridge là gì?**  
Thành phần chuyển lời gọi/sự kiện từ một logging API sang API khác để dùng backend đã chọn.

**2. log4j-slf4j2-impl và log4j-to-slf4j có thể cài cùng nhau không?**  
Không. Chúng đi hai chiều ngược nhau và tạo vòng định tuyến nguy hiểm.

**3. log4j-jul khác log4j-to-jul thế nào?**  
**log4j-jul** phục vụ JUL → Log4j API; **log4j-to-jul** phục vụ Log4j API → JUL.

**4. SLF4J 1.7 dùng cùng provider với SLF4J 2 không?**  
Không nên. SLF4J 1.7 có **log4j-slf4j-impl**; SLF4J 2 dùng **log4j-slf4j2-impl**.

**5. Cài log4j-core có tự gom mọi JUL event không?**  
Không. Cần một cách tích hợp JUL, ví dụ log4j-jul và startup property/Handler bridge phù hợp.

**6. Vì sao thay JUL LogManager phải rất sớm?**  
Vì JUL có thể đã khởi tạo global manager trước main(); cấu hình muộn không chắc có hiệu lực.

**7. Bridge có bảo đảm JSON fields/Throwable/caller location giống hệt nhau không?**  
Không. Cần kiểm tra chuyển ngữ nghĩa và encoder thực tế.

**8. Có nên thêm mọi bridge vào mọi project để không mất log?**  
Không. Chỉ thêm bridge cần thiết, vẽ đúng hướng, kiểm tra duplicate và vòng lặp.

**9. Nếu mọi API đã được đưa về Log4j Core mà vẫn thiếu log, nên kiểm tra gì?**  
Logger name, LoggerConfig, level, Filter, AppenderRef, additivity, Layout, sink và collector.

**10. Bridge có thay thế policy bảo mật và audit không?**  
Không. Bridge là hạ tầng định tuyến, không tự bảo đảm redaction, durability, retention hay quyền truy cập.

## 17. Tài liệu tham khảo chính thức

- Apache Log4j — Installation: https://logging.apache.org/log4j/2.x/manual/installation.html
- Apache Log4j — Components: https://logging.apache.org/log4j/2.x/components.html
- Apache Log4j — JUL-to-Log4j bridge: https://logging.apache.org/log4j/2.x/log4j-jul.html
- Apache Log4j — Log4j-to-JUL bridge: https://logging.apache.org/log4j/2.x/log4j-to-jul.html
- Apache Log4j — Migrating from Logback: https://logging.apache.org/log4j/2.x/migrate-from-logback.html
- Apache Log4j — Migrating from SLF4J: https://logging.apache.org/log4j/2.x/migrate-from-slf4j.html

Những hướng dẫn này thuộc **Log4j 2.x**. Khi dùng version, framework hoặc container khác, cần đối chiếu cơ chế provider, dependency và hướng dẫn tích hợp của runtime đó.

## 18. Ghi nhớ chính

**Bridge chỉ chuyển nguồn log từ một API sang API khác theo một chiều**; backend quyết định level, Filter, Appender và output. Khi chọn **Log4j Core** làm đích: Log4j API đi trực tiếp, SLF4J 2 thường qua **log4j-slf4j2-impl**, JUL qua **log4j-jul**, còn những API legacy cần adapter thích hợp nếu thực sự có trong ứng dụng.

Đường định tuyến đúng phải **không vòng lặp, không nhân đôi và có thể kiểm chứng bằng log event mẫu từ từng API**. Trong ví dụ Java 17+ đã chạy, Log4j API, SLF4J và JUL cùng xuất một format qua Log4j Core, còn JUL LogManager được xác nhận là implementation của log4j-jul. Đây là tiêu chuẩn thực dụng khi đánh giá một cấu hình bridge, không chỉ dựa trên danh sách JAR đã cài.
