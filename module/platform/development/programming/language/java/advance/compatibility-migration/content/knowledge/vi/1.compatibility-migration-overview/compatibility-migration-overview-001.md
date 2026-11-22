# Tương thích và chuyển đổi phiên bản trong hệ sinh thái Java

## 1. Vì sao cần hiểu tính tương thích trước khi nâng cấp?

Một ứng dụng Java hiếm khi chỉ phụ thuộc vào JDK. Nó còn phụ thuộc vào bytecode của các thư viện, framework, plugin build, công cụ kiểm thử, máy chủ ứng dụng, hệ điều hành, image container và các dịch vụ giao tiếp qua mạng. Vì vậy, thay đổi phiên bản Java có thể ảnh hưởng đến nhiều lớp cùng lúc. Một dự án biên dịch thành công trên JDK mới vẫn có thể không khởi động được ở môi trường triển khai cũ; một thư viện giữ nguyên chữ ký API vẫn có thể thay đổi hành vi; một framework mới có thể yêu cầu cả JDK mới lẫn một namespace API khác.

**Tương thích phiên bản** là khả năng các thành phần tiếp tục phối hợp đúng khi một hoặc nhiều thành phần được thay đổi phiên bản. **Chuyển đổi phiên bản** là quá trình đưa hệ thống từ một tập phiên bản đang hoạt động sang tập phiên bản mục tiêu, đồng thời kiểm soát thay đổi về mã nguồn, bytecode, API, hành vi, dữ liệu và môi trường vận hành.

Mục tiêu của migration không chỉ là làm cho ứng dụng chạy được trên JDK mới. Hệ thống cần giữ đúng hợp đồng với người dùng và các hệ thống phụ thuộc, có thể xây dựng lặp lại trong CI, triển khai được trên môi trường đích, đồng thời có cách phát hiện và xử lý lỗi khi thay đổi.

Trong bài này, “hệ sinh thái Java” bao gồm JDK/JVM, ngôn ngữ Java, thư viện, framework, hệ thống build, công cụ phát triển và kiểm thử, nền tảng triển khai, cũng như các giao thức và định dạng dữ liệu mà ứng dụng sử dụng.

Sau khi học, người đọc có thể:

- Phân biệt các loại tương thích và xác định loại nào quan trọng với một thay đổi cụ thể.
- Giải thích quan hệ giữa phiên bản JDK, phiên bản bytecode, mức ngôn ngữ và API Java được phép sử dụng.
- Đánh giá ảnh hưởng của việc nâng cấp JDK, framework, thư viện và build tool.
- Lập ma trận phiên bản và kế hoạch migration có thể kiểm chứng.
- Nhận diện những lỗi phổ biến như `UnsupportedClassVersionError`, thay đổi `javax` sang `jakarta`, xung đột dependency và lỗi do truy cập API nội bộ.

## 2. Các chiều tương thích cần phân biệt

Không có một nhãn “compatible” duy nhất áp dụng cho mọi tình huống. Một thay đổi có thể tương thích ở cấp biên dịch nhưng không tương thích ở cấp hành vi hoặc vận hành. Trước khi nâng cấp, cần xác định thành phần nào là bên cung cấp và thành phần nào là bên tiêu thụ hợp đồng.

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ thay đổi có thể phá vỡ tương thích |
| --- | --- | --- |
| Tương thích mã nguồn (source) | Mã nguồn cũ có biên dịch được với phiên bản API/compiler mới không? | Xóa overload, đổi kiểu tham số, đổi package, tạo overload gây mơ hồ khi gọi hàm. |
| Tương thích nhị phân (binary) | Bytecode đã biên dịch có liên kết và chạy được với thư viện/runtime mới không? | Xóa method hoặc field mà bytecode cũ tham chiếu; đổi descriptor hoặc khả năng truy cập. |
| Tương thích hành vi (behavioral) | Chương trình có còn cho kết quả và tác dụng phụ như trước không? | Thay đổi giá trị mặc định, thứ tự xử lý, thuật toán, timeout hoặc cách xử lý lỗi. |
| Tương thích dữ liệu (data) | Dữ liệu đã lưu có còn đọc, ghi và diễn giải đúng không? | Đổi schema, kiểu trường, tên thuộc tính JSON hoặc định dạng serialization. |
| Tương thích giao thức (protocol/API) | Các hệ thống độc lập có tiếp tục trao đổi được không? | Đổi endpoint, header, mã lỗi, schema message hoặc quy tắc xác thực. |
| Tương thích build/tooling | Dự án có tiếp tục được build, test và đóng gói bằng toolchain mới không? | Plugin không hỗ trợ Gradle/Maven/JDK mới; annotation processor không tương thích compiler. |
| Tương thích vận hành (operational) | Ứng dụng có hoạt động đúng trong môi trường triển khai không? | Image thiếu CA certificate, thay đổi TLS mặc định, giới hạn bộ nhớ hoặc cấu hình JVM khác. |

### 2.1. Source compatibility

Source compatibility nói về khả năng biên dịch lại mã nguồn hiện có. Ví dụ, thư viện phiên bản 2 có thể vẫn cung cấp phần lớn API của phiên bản 1 nhưng đổi một constructor từ `public` thành `protected`. Mã nguồn gọi constructor đó sẽ không còn biên dịch được.

Source compatibility cũng có thể bị ảnh hưởng bởi thay đổi trong compiler hoặc ngôn ngữ. Một tên biến trước đây hợp lệ có thể trở thành từ khóa hoặc ngữ cảnh đặc biệt trong phiên bản ngôn ngữ mới. Việc thêm overload cũng có thể làm một lời gọi vốn rõ ràng trở thành mơ hồ. Vì vậy, “chỉ thêm API” không đồng nghĩa tuyệt đối với “không thể gây lỗi biên dịch”.

### 2.2. Binary compatibility

Binary compatibility quan tâm đến bytecode đã được biên dịch. JVM liên kết các lớp và thành viên dựa trên tên, descriptor, quyền truy cập và cấu trúc kiểu. Nếu ứng dụng đã biên dịch gọi `LibraryClient.send(String)`, nhưng thư viện mới xóa method đó hoặc thay đổi descriptor, lỗi có thể chỉ xuất hiện khi lớp được nạp hoặc method được gọi.

Một số lỗi thường gặp là `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError`, `IllegalAccessError` và `IncompatibleClassChangeError`. Chúng thường cho thấy bytecode được biên dịch dựa trên một hợp đồng khác với hợp đồng đang có trong runtime classpath. Không nên xử lý các lỗi này bằng cách thêm dependency ngẫu nhiên; cần xác định chính xác lớp và phiên bản nào đang được nạp.

Binary compatibility không đảm bảo behavioral compatibility. Một method vẫn tồn tại với cùng chữ ký nhưng thay đổi thuật toán, giá trị mặc định hoặc cách xử lý ngoại lệ thì bytecode cũ vẫn liên kết được, song ứng dụng có thể hoạt động khác.

### 2.3. Forward compatibility và backward compatibility

Hai thuật ngữ này thường bị dùng lẫn vì góc nhìn có thể thay đổi. Hãy luôn nêu rõ bên nào là phiên bản mới và bên nào là phiên bản cũ:

- **Backward compatibility (tương thích ngược):** phiên bản mới tiếp tục hỗ trợ hợp đồng hoặc dữ liệu do phiên bản cũ tạo ra. Ví dụ, dịch vụ mới vẫn đọc được message đã phát hành theo schema cũ.
- **Forward compatibility (tương thích xuôi):** thành phần cũ có thể bỏ qua hoặc xử lý an toàn dữ liệu/tính năng được tạo bởi thành phần mới. Ví dụ, consumer cũ bỏ qua trường JSON không nhận biết.

Không phải mọi giao thức hay định dạng đều tự động có hai đặc tính này. Một parser nghiêm ngặt có thể từ chối trường mới; một consumer cũ có thể hiểu sai giá trị enum mới. Khi thiết kế API hoặc schema, cần định nghĩa rõ quy tắc cho trường không biết, giá trị enum mới, trường bắt buộc và giá trị mặc định.

### 2.4. Tương thích dữ liệu và giao thức

Đối với ứng dụng doanh nghiệp, hợp đồng dữ liệu thường tồn tại lâu hơn một lần triển khai. JSON, XML, message queue, bảng cơ sở dữ liệu và file xuất có thể được tạo bởi nhiều phiên bản ứng dụng khác nhau. Một bản nâng cấp chỉ thay đổi Java class nhưng làm đổi tên trường JSON vẫn là một thay đổi hợp đồng bên ngoài.

Với Java Serialization, `serialVersionUID` và cấu trúc lớp ảnh hưởng đến khả năng đọc stream cũ. Với JSON, cần xem xét tên trường, kiểu dữ liệu, nullability, enum, ngày giờ và quy tắc bỏ qua trường không biết. Với database, cần cân nhắc khả năng ứng dụng cũ và mới cùng chạy trong giai đoạn rollout.

Một chiến lược phổ biến là **expand–migrate–contract**: trước hết mở rộng schema để cả phiên bản cũ và mới cùng hoạt động; sau đó chuyển dữ liệu và triển khai ứng dụng mới; cuối cùng mới loại bỏ cấu trúc cũ khi không còn consumer sử dụng. Cách này giảm rủi ro khi không thể nâng cấp tất cả thành phần cùng lúc.

## 3. JDK, Java language level và bytecode không phải một khái niệm

Khi nói “dự án dùng Java 21”, cần làm rõ ít nhất ba điều:

1. JDK nào chạy Gradle/Maven và các công cụ build?
2. Compiler sử dụng mức ngôn ngữ và API Java nào để biên dịch mã nguồn?
3. JVM thấp nhất nào được hỗ trợ khi chạy artifact đã tạo?

Ngoài ra, mỗi thư viện trong dependency graph có thể được biên dịch bằng một phiên bản Java khác. Một ứng dụng đặt target Java 17 vẫn không thể chạy trên Java 17 nếu nó phụ thuộc vào thư viện chỉ có bytecode Java 21.

### 3.1. JVM và class-file version

`javac` chuyển mã nguồn Java thành bytecode trong file `.class`. Mỗi class file có một giá trị major version cho biết định dạng bytecode mà JVM cần hiểu. Một số mốc thường gặp:

| Phiên bản Java | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Ví dụ, nếu một class được biên dịch thành bytecode Java 21 rồi chạy trên JVM Java 17, JVM cũ không hiểu class-file version 65 và có thể ném `UnsupportedClassVersionError`. Đây là lỗi khác với `NoSuchMethodError`: lỗi đầu tiên thường chỉ ra bytecode mới hơn runtime, còn lỗi thứ hai thường chỉ ra hợp đồng classpath không khớp.

Có thể kiểm tra class file bằng:

```bash
javap -verbose com.example.Main
```

Trong output, tìm `major version`. Với JAR, có thể giải nén hoặc dùng `javap` với classpath phù hợp để kiểm tra lớp cụ thể. Đừng suy luận toàn bộ tương thích của ứng dụng chỉ từ class chính: dependency cũng chứa class file riêng.

### 3.2. `--source`, `--target` và `--release`

Các tùy chọn compiler giải quyết những vấn đề khác nhau:

- `--source` giới hạn cú pháp/ngôn ngữ Java được chấp nhận.
- `--target` chỉ định định dạng bytecode đích.
- `--release` kết hợp mức ngôn ngữ, bytecode và tập API Java SE được phép sử dụng cho release đó.

Khi cần tạo artifact tương thích với một release Java cũ hơn, `--release` thường là lựa chọn rõ ràng hơn so với chỉ đặt `source` và `target`. Ví dụ, build bằng JDK 21 với `--release 17` sẽ kiểm soát việc dùng API Java SE theo Java 17, thay vì vô tình biên dịch lời gọi tới API chỉ có trên JDK 21 rồi tạo bytecode đích cũ.

Tuy nhiên, `--release 17` không biến mọi dependency thành thư viện tương thích Java 17. Nó cũng không kiểm tra mọi khác biệt hành vi của JVM, thư viện bên thứ ba, reflection, cấu hình hệ thống hay dịch vụ ngoài. Cần kiểm tra riêng toàn bộ dependency và môi trường chạy.

### 3.3. Dùng toolchain để cố định JDK build

Một dự án có thể được build trên nhiều máy. Nếu mỗi máy tự dùng JDK mặc định khác nhau, kết quả có thể khác nhau hoặc chỉ một số máy build được. Gradle Java Toolchains giúp khai báo JDK dùng cho compile/test/run task thay vì phụ thuộc vào `JAVA_HOME` của từng máy.

Ví dụ Gradle Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
```

Ví dụ này dùng toolchain JDK 21 để thực hiện build nhưng tạo bytecode và giới hạn API Java SE ở mức 17. Cần bảo đảm các task khác, plugin, annotation processor và test runtime cũng phù hợp với lựa chọn đó. Nếu mục tiêu thực tế là chạy Java 21, hãy đặt release tương ứng và kiểm thử trên JVM Java 21.

Với Maven Compiler Plugin, có thể khai báo release trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

Cấu hình compiler chỉ là một phần của toolchain. Maven hoặc Gradle bản thân cũng cần chạy trên một JDK được phiên bản build tool hỗ trợ. Hãy phân biệt **JVM chạy build tool** với **JDK toolchain dùng để biên dịch và chạy test**.

### 3.4. Preview features và incubator APIs

Một số tính năng Java được phát hành dưới dạng preview hoặc incubator trước khi trở thành API ổn định. Preview feature thường cần bật rõ ràng ở cả bước biên dịch và chạy, đồng thời gắn với một release cụ thể. Không nên xem bytecode dùng preview feature như artifact tương thích rộng rãi giữa nhiều JDK.

Nếu ứng dụng dùng preview/incubator API, cần ghi nhận đây là ràng buộc migration riêng: xác định phiên bản JDK chính xác, cờ compiler/runtime, phạm vi sử dụng và kế hoạch thay thế khi API thay đổi hoặc bị loại bỏ.

## 4. Các thay đổi thường gặp khi nâng cấp JDK

Nâng cấp JDK có thể làm lộ ra vấn đề đã tồn tại nhưng trước đó chưa bị kiểm tra nghiêm ngặt. Những khu vực sau cần được rà soát có chủ đích.

### 4.1. API bị deprecated, loại bỏ hoặc thay đổi

API deprecated vẫn có thể hoạt động trong một release, nhưng có thể bị loại bỏ hoặc thay đổi ở release sau. Khi migration qua nhiều LTS, cần đọc migration guide và release notes cho các phiên bản trung gian có ảnh hưởng, thay vì chỉ đọc ghi chú của phiên bản đích.

Các công cụ hữu ích gồm:

```bash
jdeprscan --release 21 application.jar
jdeps --jdk-internals application.jar
```

`jdeprscan` hỗ trợ tìm một số tham chiếu tới API đã deprecated trong artifact. `jdeps --jdk-internals` giúp phát hiện phụ thuộc vào API nội bộ của JDK. Đây là phân tích tĩnh; chúng không thể phát hiện đầy đủ mọi lời gọi qua reflection, cấu hình runtime hoặc đường đi chỉ xuất hiện trong production. Kết quả cần được đối chiếu với kiểm thử thực tế.

### 4.2. Truy cập API nội bộ và hệ thống module

Từ Java 9, Java Platform Module System (JPMS) đưa ra ranh giới module và cơ chế encapsulation mạnh hơn. Ứng dụng hoặc thư viện từng truy cập sâu vào package nội bộ của JDK có thể bắt đầu nhận warning hoặc lỗi truy cập khi chạy trên JDK mới.

Các lỗi như `InaccessibleObjectException` thường xuất hiện khi thư viện dùng reflection để truy cập thành viên không được mở cho module của nó. Cờ `--add-opens` có thể hữu ích như biện pháp chuyển tiếp có kiểm soát, nhưng nên xem đó là dấu hiệu cần xử lý dependency hoặc thay thế cách truy cập. Duy trì nhiều cờ mở nội bộ lâu dài làm tăng phụ thuộc vào chi tiết triển khai của JDK.

### 4.3. Các module Java EE/CORBA từng đi kèm JDK

Một số module Java EE và CORBA từng có trong các JDK cũ đã bị tách khỏi JDK tiêu chuẩn ở các release mới hơn. Ví dụ, ứng dụng cũ có thể dựa vào JAXB API/implementation có sẵn trong JDK 8, nhưng không còn tìm thấy chúng mặc định trên JDK 11 trở lên.

Khi gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` sau khi nâng cấp, hãy kiểm tra xem ứng dụng có đang dựa vào module từng được đóng gói trong JDK cũ hay không. Nếu API đó vẫn cần thiết, cần khai báo dependency phù hợp và chọn phiên bản tương thích với JDK/framework mục tiêu.

### 4.4. Namespace `javax` và `jakarta`

Một thay đổi lớn trong hệ sinh thái Jakarta EE là việc chuyển nhiều API enterprise từ namespace `javax.*` sang `jakarta.*`. Ví dụ:

| API | Namespace cũ | Namespace mới |
| --- | --- | --- |
| Servlet | `javax.servlet.*` | `jakarta.servlet.*` |
| Persistence | `javax.persistence.*` | `jakarta.persistence.*` |
| Validation | `javax.validation.*` | `jakarta.validation.*` |
| JAX-RS | `javax.ws.rs.*` | `jakarta.ws.rs.*` |

Đây là thay đổi package ở cấp mã nguồn và binary. Class `javax.persistence.Entity` và `jakarta.persistence.Entity` là hai kiểu khác nhau; thư viện/framework mong đợi namespace này không tự động tương thích với namespace kia.

Không được thay thế hàng loạt mọi chuỗi `javax` thành `jakarta`. Java SE vẫn có các package `javax` hợp lệ, chẳng hạn một số API trong `javax.crypto`, `javax.net` và `javax.sql`. Chỉ chuyển những API thuộc hệ sinh thái đã chuyển namespace và theo đúng phiên bản framework mục tiêu.

Khi nâng cấp framework có bước chuyển Jakarta, cần đồng bộ dependency, import, annotation, cấu hình, plugin sinh mã, test library và runtime container. Trộn thư viện dựa trên hai thế hệ namespace trong cùng một luồng tích hợp thường dẫn đến lỗi kiểu dữ liệu hoặc class loading khó truy tìm.

### 4.5. Thay đổi mặc định của JVM và môi trường

JDK mới có thể thay đổi mặc định liên quan đến TLS, chứng thư số, thuật toán mã hóa, charset, locale, timezone database, garbage collector, JIT, container awareness hoặc giới hạn tài nguyên. Không phải mọi thay đổi đều phá vỡ tương thích, nhưng chúng có thể làm lộ giả định cũ của ứng dụng.

Ví dụ, kết nối HTTPS có thể thất bại vì máy chủ chỉ hỗ trợ bộ mã hóa hoặc giao thức đã bị vô hiệu hóa trong JDK mới. Một ứng dụng có thể dùng nhiều CPU hoặc bộ nhớ hơn do cách nhận diện container thay đổi. Cần kiểm tra log, metric, handshake và cấu hình JVM trong môi trường gần production, thay vì chỉ dựa vào kết quả unit test.

## 5. Tương thích giữa framework, thư viện và build tool

JDK chỉ là một trục trong ma trận phiên bản. Một framework có thể yêu cầu JDK tối thiểu, một dòng Spring Framework nhất định, một phiên bản servlet container, hoặc namespace API mới. Plugin build và công cụ kiểm thử cũng có ma trận hỗ trợ riêng.

### 5.1. Lập ma trận phiên bản

Trước khi nâng cấp, hãy ghi lại các thành phần có ảnh hưởng và phiên bản hiện tại/mục tiêu. Ví dụ:

| Thành phần | Phiên bản hiện tại | Phiên bản mục tiêu | Điều cần xác nhận |
| --- | --- | --- | --- |
| JDK chạy build | JDK 17 | JDK 21 | Gradle/Maven và plugin có chạy được trên JDK 21 không? |
| Java release | 17 | 21 hoặc 17 | Artifact cần hỗ trợ JVM thấp nhất nào? |
| Gradle/Maven | Bản đang dùng | Bản hỗ trợ JDK mục tiêu | Wrapper, daemon, plugin và lifecycle có tương thích không? |
| Spring Boot | Dòng hiện tại | Dòng mục tiêu | JDK tối thiểu, Spring Framework, Jakarta và container yêu cầu gì? |
| ORM/JPA | Bản hiện tại | Bản tương thích framework | Namespace, dialect, query và schema có thay đổi không? |
| Jackson/JSON | Bản hiện tại | Bản mục tiêu | Serialization, naming, date/time và polymorphism có đổi không? |
| Test stack | JUnit/Mockito/... hiện tại | Bản mục tiêu | Engine, extension, mock agent và test runtime có tương thích không? |
| Image triển khai | Base image hiện tại | Image có JRE/JDK mục tiêu | CA, timezone, user, native library và kiến trúc CPU có phù hợp không? |

Bảng trên là mẫu phân tích, không phải một bộ phiên bản tương thích sẵn. Phiên bản cụ thể phải được xác minh từ tài liệu chính thức của từng thành phần tại thời điểm migration.

### 5.2. Dependency graph và dependency mediation

Một dependency khai báo trực tiếp có thể kéo theo nhiều dependency bắc cầu (transitive dependencies). Hai thư viện có thể yêu cầu hai phiên bản khác nhau của cùng một artifact; Maven hoặc Gradle sẽ áp dụng quy tắc phân giải để chọn phiên bản. Build vẫn có thể thành công dù phiên bản được chọn không đúng với giả định của một thư viện.

Hãy xem dependency graph trước và sau migration. Với Gradle:

```bash
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

Với Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Cần chú ý dependency bị kéo bắc cầu, phiên bản bị override, artifact trùng lặp, dependency chỉ có ở test/runtime và thư viện đã ngừng hỗ trợ JDK mục tiêu. Khi dùng Spring Boot hoặc nền tảng tương tự, BOM/dependency management giúp giữ một tập phiên bản đã được kiểm thử cùng nhau. Không nên nâng riêng từng thư viện lõi ra khỏi tập quản lý nếu chưa xác nhận ma trận tương thích.

### 5.3. Framework major version và hợp đồng migration

Major version thường chứa thay đổi có thể phá vỡ API hoặc hành vi, nhưng không phải mọi dự án đều tuân thủ SemVer giống nhau. Release notes và migration guide mới là căn cứ để xác định thay đổi thực tế.

Với framework, hãy tìm ít nhất các nội dung sau:

- JDK tối thiểu và phiên bản framework nền mà release yêu cầu.
- Package hoặc annotation đã đổi, bị xóa hay đổi mặc định.
- Cấu hình cũ còn được hỗ trợ hay cần chuyển sang cấu hình mới.
- Thay đổi vòng đời bean, transaction, validation, security, serialization hoặc exception handling.
- Thay đổi API extension mà ứng dụng hoặc thư viện nội bộ đang sử dụng.
- Phiên bản servlet container, driver, database và plugin cần đồng bộ.

Không nên chỉ sửa lỗi compile cho đến khi build xanh. Một cấu hình bảo mật hoặc transaction có thể vẫn biên dịch nhưng thay đổi hiệu lực khi chạy.

### 5.4. Build tool và plugin

Gradle/Maven có phiên bản runtime riêng và các plugin mở rộng riêng. Nâng JDK trước khi nâng build tool có thể khiến wrapper hoặc plugin không khởi động được. Ngược lại, nâng build tool mà không kiểm tra plugin có thể làm thay đổi task, cấu hình hoặc convention hiện có.

Với Gradle, kiểm tra ma trận Java compatibility của Gradle, phiên bản wrapper trong `gradle-wrapper.properties`, plugin trong `plugins {}` và các plugin nội bộ. Với Maven, kiểm tra Maven runtime, Maven Wrapper, Maven Compiler/Surefire/Failsafe Plugin, annotation processor và Maven extensions.

Các thành phần dễ bị bỏ sót gồm Lombok, MapStruct, QueryDSL, Kotlin compiler plugin, Error Prone, JaCoCo, SpotBugs, formatter, code generator, test engine và công cụ đóng gói native. Chúng có thể tương tác trực tiếp với compiler API hoặc bytecode format nên cần phiên bản hỗ trợ JDK mới.

## 6. Quy trình migration có kiểm soát

Một migration tốt bắt đầu bằng việc xác định hợp đồng và phạm vi ảnh hưởng, sau đó thay đổi theo các bước có thể quan sát. Không nên nâng đồng thời quá nhiều trục nếu đội phát triển không thể quy lỗi về đúng thay đổi.

### Bước 1: Xác định mục tiêu và ràng buộc

Ghi rõ lý do nâng cấp: kết thúc hỗ trợ của JDK cũ, yêu cầu bảo mật, framework mới, hiệu năng, tính năng ngôn ngữ hay chuẩn hóa môi trường. Xác định:

- Phiên bản JDK chạy build và phiên bản JDK chạy production.
- Phiên bản Java thấp nhất mà artifact cần hỗ trợ.
- Framework và dependency bắt buộc phải giữ hoặc phải nâng.
- Nền tảng triển khai, hệ điều hành, container và kiến trúc CPU.
- Consumer bên ngoài, định dạng dữ liệu và giao thức cần giữ tương thích.
- Thời hạn hỗ trợ, cửa sổ triển khai và phương án rollback.

Nếu chưa xác định được JVM thấp nhất của consumer, chưa thể kết luận artifact có thể đổi bytecode sang release mới.

### Bước 2: Lập baseline có thể tái tạo

Trước khi sửa, lưu lại trạng thái build/test hiện tại, dependency graph, cấu hình runtime, startup log và các chỉ số vận hành quan trọng. Ghi nhận test nào đang fail từ trước để không quy nhầm lỗi cũ cho migration.

Đảm bảo có thể tái tạo build từ wrapper và cấu hình repository đã được kiểm soát. Nếu build phụ thuộc vào JDK cài ngẫu nhiên trên máy cá nhân, hãy chuẩn hóa toolchain/CI trước hoặc ghi nhận rõ hạn chế này.

### Bước 3: Kiểm tra đường nâng cấp của toolchain

Xác minh phiên bản Gradle/Maven và plugin có thể chạy trên JDK mục tiêu. Nếu không, nâng wrapper/build tool và plugin theo các bước tương thích được hỗ trợ. Sau mỗi thay đổi, chạy build tối thiểu để tách lỗi của build system khỏi lỗi của mã nguồn.

Cần kiểm tra cả daemon JVM, compiler toolchain, test JVM, task chạy code generator và JVM trong CI. Một task có thể vô tình dùng JDK mặc định khác với task compile.

### Bước 4: Nâng dependency theo tập tương thích

Đọc release notes/migration guide của framework chính, sau đó xác định BOM hoặc dependency platform phù hợp. Nâng các thư viện có ràng buộc chặt cùng nhau, chẳng hạn framework, persistence provider, servlet API, validation provider và test integration.

Sau khi cập nhật, kiểm tra dependency graph để tìm phiên bản bị override hoặc xung đột. Không dùng exclusion hoặc force version như cách làm build xanh tạm thời nếu chưa hiểu thư viện nào cần artifact đó và tại sao.

### Bước 5: Sửa mã nguồn và cấu hình có chủ đích

Xử lý compiler error, deprecated API, package namespace, cấu hình bị loại bỏ và thay đổi hợp đồng. Mỗi thay đổi nên gắn với một nguyên nhân từ release notes, compiler hoặc test. Khi thay đổi JSON/schema/database, cần đánh giá consumer và khả năng chạy đồng thời giữa phiên bản cũ và mới.

Tránh thay thế hàng loạt theo tên package hoặc tên method khi chưa phân biệt API thuộc Java SE, Jakarta EE hay thư viện riêng. Chạy formatter và generator đúng phiên bản sau khi cập nhật toolchain.

### Bước 6: Kiểm chứng theo nhiều lớp

Một migration cần nhiều loại bằng chứng:

1. **Build:** clean build bằng wrapper, đúng JDK và không dựa vào output cũ.
2. **Static analysis:** kiểm tra deprecated API, JDK internal API, dependency graph và cấu hình không còn được hỗ trợ.
3. **Unit test:** xác nhận logic cục bộ và các trường hợp biên.
4. **Integration test:** kiểm tra database, message broker, HTTP client/server, serialization, security và framework wiring.
5. **Contract test:** xác nhận API/schema mà consumer khác đang sử dụng.
6. **Runtime test:** chạy artifact bằng đúng JVM và image triển khai dự kiến.
7. **Performance/operational test:** so sánh startup, throughput, latency, memory, GC, thread và lỗi kết nối với baseline.

Build xanh chỉ chứng minh các bước build đã hoàn tất. Nó không tự chứng minh tương thích dữ liệu, giao thức hay hành vi trong production.

### Bước 7: Triển khai có khả năng quan sát và rollback

Nếu hệ thống hỗ trợ, triển khai canary hoặc theo từng nhóm instance. Theo dõi startup failure, exception, log cảnh báo, tỷ lệ lỗi, latency, tài nguyên JVM, kết nối database và message backlog. Với thay đổi schema, phải bảo đảm rollback ứng dụng vẫn đọc được dữ liệu đã được phiên bản mới ghi.

Rollback cần được thiết kế trước: giữ artifact cũ, biết image/JDK cũ còn khả dụng hay không, và xác định migration dữ liệu nào có thể đảo ngược. Không phải thay đổi schema nào cũng rollback an toàn; đôi khi cần một bản sửa tiến về phía trước (roll-forward).

### Bước 8: Hoàn tất và chuẩn hóa

Sau khi ổn định, cập nhật tài liệu build, JDK yêu cầu, image base, CI, hướng dẫn phát triển, dependency policy và quy trình phát hành. Xóa dần cờ tương thích tạm thời như `--add-opens` khi không còn cần thiết. Ghi lại các ràng buộc còn tồn tại để lần nâng cấp tiếp theo không phải khám phá lại từ đầu.

## 7. Chiến lược nâng cấp: một bước hay nhiều chặng?

Có hai cách tiếp cận phổ biến:

- **Nâng trực tiếp (big-bang):** chuyển nhiều thành phần trong một lần phát hành. Cách này có thể phù hợp với ứng dụng nhỏ, ít consumer và có kiểm thử tự động tốt. Rủi ro là khi có lỗi, nhiều thay đổi cùng xuất hiện khiến việc truy nguyên nguyên nhân khó hơn.
- **Nâng theo chặng (incremental):** chuẩn hóa build tool, nâng JDK, nâng framework, rồi thay đổi schema hoặc API theo từng giai đoạn. Cách này tạo nhiều điểm kiểm soát và dễ khoanh vùng lỗi, nhưng có thể phải duy trì trạng thái tương thích trung gian lâu hơn.

Có thể dùng ma trận sau để chọn cách làm:

| Điều kiện | Hướng tiếp cận thường phù hợp |
| --- | --- |
| Ứng dụng nhỏ, ít dependency, không có consumer độc lập | Có thể nâng trực tiếp nếu có test và rollback đáng tin cậy. |
| Framework major version kèm namespace/API migration | Chia chặng để tách thay đổi toolchain khỏi thay đổi framework. |
| Nhiều dịch vụ trao đổi message hoặc dùng chung database | Thiết kế tương thích dữ liệu/giao thức trước, triển khai theo thứ tự producer-consumer. |
| Có thư viện nội bộ được nhiều ứng dụng dùng | Kiểm tra binary/source compatibility và phát hành thư viện theo lộ trình riêng. |
| Môi trường production không thể dừng đồng loạt | Dùng rollout nhiều bước và hợp đồng tương thích giữa phiên bản cũ/mới. |

Không có thứ tự nâng cấp cố định cho mọi dự án. Một nguyên tắc hữu ích là nâng thành phần nền mà các bước sau phụ thuộc vào trước, nhưng chỉ khi phiên bản mới của thành phần đó vẫn hỗ trợ các thành phần còn lại trong giai đoạn chuyển tiếp.

## 8. Ví dụ phân tích một migration Java 17 lên Java 21

Giả sử một dịch vụ đang chạy Java 17, build bằng Gradle, dùng Spring Boot, Hibernate, Jackson và JUnit. Mục tiêu là chạy production bằng Java 21.

Trước khi thay đổi, nhóm cần trả lời:

- Phiên bản Gradle wrapper hiện tại có hỗ trợ chạy trên JDK 21 không?
- Phiên bản Spring Boot đang dùng có hỗ trợ Java 21 và dependency nền tương ứng không?
- Hibernate/Jakarta, driver database, Jackson và test stack có tương thích với framework mục tiêu không?
- Có dependency nào được biên dịch bằng Java cao hơn 21 hoặc truy cập API nội bộ JDK không?
- Image production có JRE 21, chứng thư, timezone và native library phù hợp không?
- Có consumer nào cần tiếp tục chạy artifact hoặc đọc dữ liệu được tạo bởi phiên bản cũ không?

Một kế hoạch khả thi có thể gồm:

1. Chạy build/test baseline trên Java 17 và lưu dependency graph.
2. Kiểm tra Gradle wrapper/plugin; nâng chúng đến phiên bản hỗ trợ JDK 21 nếu cần.
3. Chạy build bằng JDK 21 nhưng tạm giữ Java release 17 nếu sản phẩm vẫn phải phát hành artifact chạy trên Java 17.
4. Nâng framework/dependency theo BOM tương thích và xử lý migration guide.
5. Chạy test trên cả JVM thấp nhất được hỗ trợ và JVM 21 trong giai đoạn chuyển tiếp.
6. Khi consumer đã sẵn sàng, chuyển release target sang 21 nếu sản phẩm quyết định bỏ hỗ trợ Java 17.
7. Cập nhật CI, container image, production runtime và tài liệu vận hành.

Điểm cần chú ý: “build bằng JDK 21” và “yêu cầu người dùng chạy Java 21” là hai quyết định khác nhau. Nếu vẫn cần hỗ trợ Java 17, cần duy trì `--release 17` và kiểm tra dependency cũng chạy được trên Java 17. Nếu chuyển artifact sang bytecode 21, mọi môi trường chạy phải có JVM tương thích.

## 9. Chẩn đoán lỗi tương thích thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | JVM chạy thấp hơn class-file version của một lớp | Xác định class gây lỗi, kiểm tra major version và JVM thực tế của process. |
| `NoSuchMethodError` | Runtime nạp phiên bản thư viện thiếu method mà bytecode cần | Kiểm tra dependency tree, classpath và nguồn nạp class. |
| `NoClassDefFoundError` / `ClassNotFoundException` | Thiếu class ở runtime, dependency bị loại hoặc API không còn đi kèm JDK | Kiểm tra runtime scope, packaging và module/dependency đã bị tách khỏi JDK. |
| `InaccessibleObjectException` | Reflection truy cập thành viên/package bị encapsulate | Xác định thư viện thực hiện reflection; nâng/thay thư viện hoặc dùng mở package tạm thời có kiểm soát. |
| `ClassCastException` giữa hai kiểu có tên giống nhau | Hai classloader hoặc hai namespace/version khác nhau | Kiểm tra classloader, dependency trùng và `javax`/`jakarta`. |
| `NoSuchFieldError` hoặc `AbstractMethodError` | Binary contract giữa các module không khớp | Kiểm tra phiên bản API/implementation và thứ tự classpath. |
| Build thành công nhưng test/runtime thất bại | Compile classpath và runtime classpath khác nhau; cấu hình hoặc hành vi đổi | Chạy test bằng đúng toolchain, kiểm tra runtime dependency và cấu hình môi trường. |
| TLS/HTTPS handshake thất bại | Khác biệt giao thức, cipher, certificate hoặc truststore | Kiểm tra handshake, certificate chain, truststore và policy của JDK. |
| JSON hoặc message không đọc được | Schema/serialization thay đổi không tương thích | So sánh payload thực tế, schema và phiên bản producer/consumer. |

Khi điều tra, cần ghi nhận JVM thực tế của tiến trình, không chỉ JDK cài trên máy. Có thể dùng `java -version`, kiểm tra cấu hình service/container và log startup. Với classpath, hãy xác định chính xác JAR được nạp; việc nhìn thấy nhiều phiên bản trong thư mục cache không chứng minh phiên bản nào đang được dùng.

## 10. Những sai lầm cần tránh

**Chỉ đổi `JAVA_HOME` rồi kết luận đã migration.** JDK chạy build, compiler toolchain, test runtime và production runtime có thể khác nhau. Phải xác minh từng nơi.

**Chỉ đặt `source`/`target` mà không kiểm soát API.** Điều này có thể tạo bytecode cũ nhưng vẫn tham chiếu API mới hơn. Dùng `--release` khi phù hợp và kiểm tra dependency.

**Nâng tất cả dependency lên phiên bản mới nhất.** “Mới nhất” không đồng nghĩa với “tương thích với nhau”. Hãy dùng ma trận hỗ trợ, BOM và release notes.

**Ép một phiên bản dependency để dập lỗi.** Force/exclude có thể che giấu xung đột và khiến một module khác hỏng ở runtime. Phải hiểu dependency nào yêu cầu phiên bản nào.

**Thay mọi `javax` thành `jakarta`.** Hai namespace có phạm vi khác nhau; Java SE vẫn giữ nhiều package `javax`. Chỉ chuyển API thuộc Jakarta migration.

**Dùng `--add-opens` làm giải pháp lâu dài.** Cờ này có thể giúp chuyển tiếp, nhưng nó duy trì phụ thuộc vào cấu trúc nội bộ và có thể trở thành gánh nặng ở lần nâng cấp tiếp theo.

**Chỉ chạy unit test.** Unit test không bao phủ đầy đủ database, message broker, HTTP contract, TLS, container, serialization và hành vi vận hành.

**Không thử rollback.** Một bản nâng cấp có thể thay đổi dữ liệu theo cách phiên bản cũ không đọc được. Cần kiểm tra tương thích khi chạy song song và kế hoạch khôi phục.

## 11. Nguyên tắc thiết kế để migration sau dễ hơn

Khả năng nâng cấp không chỉ được quyết định ở thời điểm migration. Kiến trúc và thói quen phát triển hằng ngày có thể làm chi phí chuyển đổi thấp hơn:

- Khai báo phiên bản JDK, build tool và plugin rõ ràng bằng wrapper/toolchain; tránh phụ thuộc vào cấu hình máy cá nhân.
- Quản lý phiên bản thư viện tập trung bằng BOM hoặc version catalog; hạn chế khai báo trùng và override không có lý do.
- Tránh phụ thuộc vào JDK internal API, reflection sâu và hành vi không được tài liệu hóa.
- Đóng gói hợp đồng API/schema có version; kiểm thử consumer-provider và giữ khả năng đọc dữ liệu cũ trong thời gian cần thiết.
- Dùng test tích hợp cho các ranh giới quan trọng: database, HTTP, messaging, serialization, security và framework wiring.
- Theo dõi warning/deprecation và cập nhật dependency định kỳ thay vì để nhiều release tích tụ thành một migration lớn.
- Tách thay đổi mã nguồn khỏi thay đổi dữ liệu/giao thức khi có thể; mỗi bước nên có cách xác nhận và phương án phục hồi.
- Ghi lại các ràng buộc phiên bản của module nội bộ để consumer biết JDK, framework và dependency tối thiểu.

## 12. Nguồn tham khảo kỹ thuật

Khi thực hiện migration thật, hãy dùng tài liệu theo đúng phiên bản đang triển khai vì ma trận hỗ trợ và hướng dẫn có thể thay đổi:

- **Java SE Migration Guide:** hướng dẫn thay đổi giữa các release của JDK, API bị loại bỏ và các vấn đề cần kiểm tra: <https://docs.oracle.com/en/java/javase/21/migrate/>.
- **OpenJDK JEP Index:** mô tả mục tiêu và thay đổi của các tính năng/nâng cấp nền tảng Java: <https://openjdk.org/jeps/>
- **Gradle Java Compatibility:** ma trận phiên bản Gradle với các JDK có thể chạy Gradle và dùng toolchain: <https://docs.gradle.org/current/userguide/compatibility.html>
- **Maven Compiler Plugin:** cấu hình compiler, release và toolchain: <https://maven.apache.org/plugins/maven-compiler-plugin/>
- **Spring Boot System Requirements:** yêu cầu Java và phiên bản build tool theo từng release Spring Boot: <https://docs.spring.io/spring-boot/system-requirements.html>

Tài liệu tham khảo cần được chọn theo phiên bản cụ thể. Trang `current` có thể đã mô tả release mới hơn phiên bản mà dự án đang sử dụng; hãy mở tài liệu tương ứng với đúng major/minor version trước khi đưa ra quyết định.

## Kết luận

Tương thích phiên bản là thuộc tính của toàn bộ hệ thống hợp tác, không phải riêng mã nguồn Java hay JDK. Một migration an toàn cần xác định rõ hợp đồng mã nguồn, bytecode, hành vi, dữ liệu, giao thức, build và vận hành; sau đó nâng cấp theo ma trận phiên bản đã xác minh và kiểm chứng bằng artifact chạy trong môi trường thực tế.

Khi đánh giá một đề xuất nâng cấp, hãy luôn hỏi ba câu: **thành phần nào thay đổi, hợp đồng nào có thể bị ảnh hưởng, và bằng chứng nào chứng minh consumer vẫn hoạt động đúng?** Trả lời được ba câu này giúp biến việc nâng cấp từ một thao tác thay version thành một quá trình kỹ thuật có thể kiểm soát.
