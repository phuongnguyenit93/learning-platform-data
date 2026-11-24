# Tránh ghi metadata của framework kiểm thử hoặc công cụ phát triển không cần thiết

Native Image Tracing Agent ghi nhận những thao tác động mà static analysis có thể không tự suy ra, chẳng hạn reflection, JNI, dynamic proxy và truy cập resource. Agent quan sát ứng dụng khi chạy trên JVM rồi tạo reachability metadata để dùng trong quá trình build native. Nếu chỉ chạy toàn bộ test suite hoặc khởi động ứng dụng trong môi trường phát triển, kết quả có thể chứa nhiều metadata do JUnit, Mockito, test fixture, Spring Boot DevTools hoặc công cụ chẩn đoán tạo ra.

Metadata thừa làm cấu hình khó review, có thể giữ lại những kiểu không cần trong production và khiến việc xác định metadata thật sự cần thiết trở nên khó khăn. Cách xử lý là **thu thập theo luồng chạy gần với production, lọc theo caller khi phù hợp, lọc theo target khi có chủ đích, rồi kiểm chứng native executable bằng các luồng nghiệp vụ thật**.

Bài này tập trung vào các bộ lọc chính thức của GraalVM Tracing Agent, cách tránh ghi nhận metadata từ framework kiểm thử/công cụ phát triển và những rủi ro khi lọc quá rộng.

## 1. Vì sao metadata tracing có thể chứa dữ liệu không cần thiết?

Tracing Agent chạy trong một JVM thông thường. Mỗi khi ứng dụng thực hiện một thao tác động, agent quan sát caller và target rồi quyết định có ghi thao tác đó vào metadata hay không.

Một ứng dụng Spring Boot có thể được chạy trong nhiều bối cảnh:

- JVM production-like chạy JAR đã đóng gói, chỉ có runtime dependencies.
- JVM test chạy cùng JUnit, Mockito, AssertJ, Testcontainers hoặc thư viện test khác.
- JVM phát triển chạy với DevTools, restart class loader, debugger, profiler hoặc hot reload.
- JVM chạy các công cụ migration, code generation, kiểm tra schema hoặc diagnostic.
- JVM khởi chạy qua Maven/Gradle test worker, IDE hoặc một wrapper có thêm dependency.

Nếu gắn Tracing Agent vào test JVM, agent có thể nhìn thấy các truy cập động do framework test thực hiện. Ví dụ, JUnit có thể dùng reflection để tìm test method; Mockito/Byte Buddy có thể tạo class proxy; thư viện assertion có thể đọc field; DevTools có thể kiểm tra class loader hoặc resource. Những thao tác này có thể xuất hiện trong metadata dù ứng dụng production không cần chúng.

### Ví dụ dữ liệu bị nhiễu

Giả sử ứng dụng có một đường nghiệp vụ thực tế:

~~~text
HTTP request
  -> OrderController
  -> OrderService
  -> PaymentAdapter
  -> đọc class metadata của PaymentDetails
~~~

Nhưng test suite còn chạy:

~~~text
JUnit engine
  -> tìm test method bằng reflection
  -> Mockito tạo mock
  -> Byte Buddy sinh class
  -> AssertJ đọc property để tạo failure description
~~~

Nếu hai nhóm chạy cùng một lần tracing, metadata có thể trộn lẫn các truy cập của ứng dụng với truy cập chỉ phục vụ test. Điều này không nhất thiết làm native build thất bại, nhưng khiến metadata lớn hơn và khó hiểu hơn.

## 2. Caller và target: hai câu hỏi khác nhau khi lọc

GraalVM cung cấp hai loại filter cho Tracing Agent.

**Caller-based filter** trả lời: *Class nào đã thực hiện thao tác động?*

Agent xác định method thực hiện truy cập (caller method), lấy class khai báo method đó rồi so khớp với rule. Nếu caller thuộc package `org.junit`, thao tác có thể bị loại khỏi metadata dù target là class ứng dụng.

**Access filter** trả lời: *Class nào là đích của thao tác động?*

Filter này xét class được truy cập, không xét class gọi thao tác. Nếu target thuộc package test fixture, có thể loại target đó khỏi metadata bất kể caller là ai.

| Tiêu chí | Caller filter | Access filter |
| --- | --- | --- |
| Lọc theo | Class chứa method thực hiện thao tác động | Class là đích được truy cập |
| Dùng để loại | Thao tác do framework test/devtools khởi phát | Test-only target hoặc class không thuộc runtime scope |
| Tùy chọn agent | `caller-filter-file` | `access-filter-file` |
| Ví dụ | Bỏ reflection do JUnit thực hiện | Bỏ target nằm trong package test fixture |
| Rủi ro | Có thể bỏ thao tác mà framework thực hiện nhưng ứng dụng production cũng cần theo cùng đường gọi | Có thể loại class ứng dụng mà runtime thực sự cần truy cập động |

**Thông thường, hãy bắt đầu bằng caller filter khi muốn loại thao tác do framework kiểm thử khởi phát.** Chỉ dùng access filter khi bạn xác định target class thực sự không thuộc phạm vi runtime của ứng dụng.

## 3. Caller filter hoạt động như thế nào?

Tạo một file JSON, ví dụ `caller-filter.json`:

~~~json
{
  "rules": [
    {
      "excludeClasses": "org.junit.**"
    },
    {
      "excludeClasses": "org.mockito.**"
    },
    {
      "excludeClasses": "org.assertj.**"
    },
    {
      "excludeClasses": "org.springframework.boot.devtools.**"
    },
    {
      "includeClasses": "com.example.billing.**"
    },
    {
      "excludeClasses": "com.example.billing.testsupport.**"
    }
  ]
}
~~~

Các rule trên minh họa cách loại thao tác phát sinh từ package test/framework/devtools và giữ lại thao tác phát sinh từ package ứng dụng. Hãy thay package bằng namespace thực tế của dự án.

### Ý nghĩa pattern

- `com.example.billing` khớp đúng class có tên đầy đủ đó.
- `com.example.billing.*` khớp các class trực tiếp trong package `com.example.billing`, không mở rộng xuống subpackage.
- `com.example.billing.**` khớp các class trong package đó và mọi subpackage ở các cấp sâu hơn.

Với ứng dụng có package con như `com.example.billing.order`, `com.example.billing.payment` và `com.example.billing.config`, pattern `.**` thường phù hợp hơn nếu muốn bao phủ toàn bộ package tree.

### Thứ tự rule rất quan trọng

Các rule được xử lý theo thứ tự xuất hiện. Rule sau có thể ghi đè một phần hoặc toàn bộ kết quả của rule trước.

Ví dụ:

~~~json
{
  "rules": [
    {
      "excludeClasses": "com.example.**"
    },
    {
      "includeClasses": "com.example.billing.**"
    },
    {
      "excludeClasses": "com.example.billing.testsupport.**"
    }
  ]
}
~~~

Kết quả:

- Mặc định loại caller thuộc `com.example` và các subpackage.
- Sau đó đưa caller thuộc `com.example.billing` trở lại.
- Cuối cùng loại riêng caller thuộc `com.example.billing.testsupport`.

Cách này hữu ích khi cần loại rộng rồi mở lại một vùng ứng dụng cụ thể. Tuy nhiên, rule nên ngắn và dễ review; nếu có nhiều ngoại lệ chồng chéo, hãy chia filter theo mục tiêu và kiểm tra thứ tự thật kỹ.

## 4. Ví dụ lọc framework kiểm thử và DevTools

Một bộ caller filter khởi đầu cho Spring Boot có thể loại các package phổ biến sau:

| Package caller | Lý do thường xuất hiện | Cần lưu ý |
| --- | --- | --- |
| `org.junit.**` | JUnit khám phá test, gọi lifecycle và truy cập test metadata | Chỉ loại nếu đang tracing test JVM; không cần loại trong capture production-only |
| `org.mockito.**` | Mockito tạo mock, inspect class và sử dụng instrumentation/code generation | Ứng dụng production có dùng Mockito không là câu hỏi riêng; thông thường không |
| `org.assertj.**` | Assertion framework inspect object để tạo kết quả so sánh | Chỉ thuộc test |
| `org.springframework.boot.devtools.**` | Restart, classloader và hỗ trợ phát triển | Chỉ loại nếu package này thực sự xuất hiện trong trace |
| `com.example.billing.testsupport.**` | Helper, fixture hoặc factory chỉ dành cho test | Dùng package test riêng, tránh để test helper nằm trong package production |
| `org.testcontainers.**` | Khởi tạo container và kiểm tra môi trường test | Không nên có trong capture production runtime |

Không sao chép danh sách trên một cách máy móc. Tracing Agent có thể ghi nhận thao tác từ package khác tùy phiên bản framework và thư viện. Hãy mở trace/metadata để xem caller thực tế trước khi thêm rule.

### Không nên loại toàn bộ Byte Buddy hoặc ASM một cách mặc định

Mockito và một số framework dùng Byte Buddy/ASM ở bên trong. Nhưng Byte Buddy cũng có thể được ứng dụng hoặc thư viện production dùng để tạo class/proxy động. Nếu loại toàn bộ caller `net.bytebuddy.**` hoặc `org.objectweb.asm.**`, bạn có thể vô tình bỏ metadata cần cho một luồng production.

Hãy loại package của framework test cụ thể trước. Chỉ loại Byte Buddy/ASM khi đã xác minh thao tác tương ứng chỉ phục vụ test/devtools và native application không cần đường đó.

## 5. Access filter: loại target class khi có bằng chứng

Caller filter không giải quyết mọi tình huống. Đôi khi caller là code ứng dụng nhưng target lại là test fixture hoặc class chỉ dùng trong môi trường phát triển. Khi đó có thể dùng access filter.

Ví dụ `access-filter.json`:

~~~json
{
  "rules": [
    {
      "excludeClasses": "com.example.billing.testsupport.**"
    },
    {
      "excludeClasses": "com.example.billing.devfixtures.**"
    }
  ]
}
~~~

Khi một thao tác động cố truy cập class thuộc các package trên, target sẽ không được đưa vào metadata do agent tạo.

### Khi nào access filter nguy hiểm?

Giả sử ứng dụng production đọc một implementation theo tên class từ cấu hình:

~~~properties
billing.payment-handler=com.example.billing.payment.CardPaymentHandler
~~~

Nếu access filter loại `com.example.billing.payment.**`, metadata cần cho handler có thể bị loại dù class đó thực sự được dùng trong production.

Vì vậy:

- Không loại package production chỉ vì tên package có vẻ nội bộ.
- Không loại target chỉ vì nó xuất hiện trong test.
- Xác minh class target có thể được truy cập ở production hay không.
- Nếu một target vừa xuất hiện trong test vừa được dùng ở production, phải giữ metadata cần thiết cho production.

## 6. Kết hợp caller filter và access filter khi chạy Tracing Agent

Agent nhận các tùy chọn filter trong chuỗi `-agentlib:native-image-agent=...`. Ví dụ chạy JAR đã đóng gói:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=caller-filter-file=src/native-image/caller-filter.json,access-filter-file=src/native-image/access-filter.json,config-output-dir=target/native-agent-config \
  -jar target/billing-service.jar \
  --spring.profiles.active=native-capture
~~~

Các điểm cần nhớ:

- Dùng `java` từ GraalVM JDK có Native Image Tracing Agent tương thích.
- Đặt `-agentlib` trước `-jar` hoặc tên main class.
- Đường dẫn filter tính từ working directory của tiến trình JVM.
- `config-output-dir` là thư mục output; agent ghi metadata khi tiến trình kết thúc bình thường.
- Profile `native-capture` chỉ là ví dụ. Hãy dùng profile không kéo theo DevTools, test fixture hoặc cấu hình phát triển.
- Không đưa credentials production thật vào quy trình tracing; dùng môi trường test/staging với dữ liệu giả và dịch vụ được kiểm soát.

Nếu muốn bổ sung kết quả từ nhiều lần chạy vào cùng bộ metadata, có thể dùng `config-merge-dir`:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=caller-filter-file=src/native-image/caller-filter.json,access-filter-file=src/native-image/access-filter.json,config-merge-dir=target/native-agent-config \
  -jar target/billing-service.jar \
  --spring.profiles.active=native-capture
~~~

Chạy các kịch bản riêng biệt để bao phủ các luồng nghiệp vụ khác nhau. Nếu cần lưu metadata định kỳ cho ứng dụng chạy lâu, agent có các tùy chọn `config-write-period-secs` và `config-write-initial-delay-secs`; kiểm tra tài liệu của GraalVM version đang dùng trước khi đưa vào script.

## 7. Chạy capture từ packaged application thay vì test classpath

Cách giảm nhiễu hiệu quả nhất là chọn đúng tiến trình để gắn agent.

### Quy trình khuyến nghị

1. Build ứng dụng JAR bằng profile production-like.
2. Không đưa test dependencies vào runtime classpath.
3. Không bật Spring Boot DevTools hoặc remote development tooling.
4. Khởi chạy chính JAR đã đóng gói bằng GraalVM JDK và Tracing Agent.
5. Gửi request qua HTTP hoặc message broker như môi trường vận hành.
6. Chạy các luồng nghiệp vụ có sử dụng reflection, serialization, proxy, resource và JNI.
7. Kết thúc tiến trình bình thường để agent ghi output.
8. Review metadata trước khi đưa vào `META-INF/native-image`.

Không nên gắn Tracing Agent vào Maven Surefire/Failsafe test JVM rồi lấy toàn bộ output làm metadata production. Test JVM có thể chứa JUnit engine, mock framework, assertion library, test container và nhiều helper chỉ có ở test scope.

### Khi test vẫn là nguồn duy nhất để kích hoạt một nhánh động

Có trường hợp test mới kích hoạt được một nhánh nghiệp vụ hiếm, nhưng nhánh đó vẫn tồn tại trong production. Không nên loại metadata chỉ vì thao tác được quan sát trong test.

Thay vào đó:

- Tạo một kịch bản capture production-like gọi đúng endpoint hoặc service đó.
- Dùng dữ liệu giả để kích hoạt nhánh.
- Gọi luồng qua entry point thật của ứng dụng.
- Dùng caller filter để bỏ truy cập do framework test tự thực hiện.
- Giữ metadata do code ứng dụng cần trong quá trình xử lý nghiệp vụ.

Mục tiêu là loại **hoạt động của công cụ kiểm thử**, không loại **khả năng ứng dụng cần để phục vụ nghiệp vụ**.

## 8. Đọc trace để tìm caller gây nhiễu trước khi thêm filter

Tracing Agent có thể xuất trace file để phân tích từng dynamic access, thay vì chỉ nhìn các file metadata đã gộp:

~~~bash
$JAVA_HOME/bin/java \
  -agentlib:native-image-agent=trace-output=target/native-agent-trace.json \
  -jar target/billing-service.jar \
  --spring.profiles.active=native-capture
~~~

Trace giúp trả lời:

- Dynamic access nào đã xảy ra?
- Caller method/class nào thực hiện access?
- Target class/member/resource nào được truy cập?
- Truy cập đó xuất hiện khi khởi động, xử lý request hay chạy test helper?

Sau đó có thể dùng `native-image-utils` để tạo metadata từ trace file:

~~~bash
native-image-utils generate \
  --trace-input=target/native-agent-trace.json \
  --output-dir=target/native-agent-config
~~~

Tên trường và cấu trúc trace có thể phụ thuộc release. Hãy dùng `native-image-utils help` và tài liệu đúng version.

### Quy trình phân loại một access

| Câu hỏi | Nếu có | Hành động |
| --- | --- | --- |
| Caller thuộc JUnit/Mockito/AssertJ? | Thao tác do framework test thực hiện | Cân nhắc caller filter |
| Caller thuộc DevTools/restart infrastructure? | Thao tác phục vụ phát triển | Tắt DevTools trong capture; nếu vẫn cần, cân nhắc caller filter |
| Caller thuộc package ứng dụng? | Có thể là luồng nghiệp vụ | Không loại chỉ vì xuất hiện trong test |
| Target thuộc test fixture? | Có thể không tồn tại trong production | Cân nhắc access filter sau khi xác minh |
| Target thuộc package production? | Có thể cần khi chạy thật | Giữ metadata và kiểm thử native |
| Caller là Byte Buddy/ASM? | Có thể là mock hoặc runtime code generation | Truy ngược ai yêu cầu tạo class; không loại package rộng ngay |

## 9. Hiểu chính xác quy tắc filter và ngoại lệ

Caller/access filter dùng cùng cấu trúc JSON với hai phần tùy chọn:

- `rules`: các rule pattern theo tên class.
- `regexRules`: các rule regular expression áp dụng lên toàn bộ fully qualified class identifier.

Ví dụ:

~~~json
{
  "rules": [
    {
      "excludeClasses": "org.junit.**"
    }
  ],
  "regexRules": [
    {
      "excludeClasses": ".*\\$\\$Generated[0-9]+"
    }
  ]
}
~~~

Nếu có `regexRules`, class chỉ được xem là included khi cả `rules` và `regexRules` đều cho phép và không phần nào loại nó. Nếu không khai báo `regexRules`, chỉ `rules` quyết định kết quả.

Một số nguyên tắc:

- Rule được xử lý theo thứ tự; rule sau có thể override rule trước.
- Có thể chỉ định nhiều `caller-filter-file`; các rule được nối theo thứ tự file truyền vào.
- Built-in caller filter chạy trước custom caller filters và custom rules có thể override kết quả built-in.
- Built-in filter đã loại một số truy cập mà Native Image hỗ trợ không cần metadata.
- `no-builtin-caller-filter` và `no-builtin-heuristic-filter` chủ yếu phục vụ thử nghiệm; output thường kém phù hợp cho build bình thường.

Không tắt built-in filters chỉ để metadata có vẻ đầy đủ hơn. Một bộ metadata có nhiều entry không đồng nghĩa với bộ metadata tốt hơn.

## 10. Review và làm sạch metadata sau khi capture

Sau khi tracing hoàn tất, hãy xem output trước khi commit. Tùy GraalVM release, metadata có thể được xuất thành `reachability-metadata.json` hoặc các file riêng như `reflect-config.json`, `resource-config.json`, `proxy-config.json`, `jni-config.json`, `serialization-config.json`.

Một vòng review có thể thực hiện như sau:

1. Liệt kê các file được tạo và so sánh với lần capture trước.
2. Tìm các package test/devtools còn xuất hiện trong metadata.
3. Mở trace để xác định caller và target của các entry đáng ngờ.
4. Xem entry đó có được ứng dụng production cần không.
5. Điều chỉnh filter hoặc capture scenario.
6. Chạy lại các luồng nghiệp vụ liên quan.
7. Build native và chạy integration test.
8. Chỉ commit metadata đã được kiểm chứng.

Không xóa hàng loạt entry chỉ dựa trên tên package. Ví dụ, `org.springframework.*` có thể chứa code framework cần metadata cho ứng dụng. Một thư viện nằm trong dependency không đồng nghĩa mọi truy cập động của nó đều là thừa.

### Kiểm tra metadata bằng diff

Nếu dùng Git:

~~~bash
git status --short
git diff -- META-INF/native-image
~~~

Có thể lưu output capture ở thư mục tạm, review rồi mới copy phần cần thiết vào vị trí metadata của module. Không để thư mục output của một lần tracing cục bộ vô tình trở thành cấu hình production mà không qua review.

## 11. Kiểm thử để phát hiện filter loại nhầm metadata

Filter tốt phải giảm nhiễu nhưng vẫn giữ mọi metadata cần cho production. Vì vậy, sau khi thay đổi filter cần chạy lại native build và kiểm thử.

Các kịch bản tối thiểu:

| Kịch bản | Mục tiêu |
| --- | --- |
| Khởi động native executable | Kiểm tra metadata cần khi bootstrap context |
| Endpoint nghiệp vụ chính | Kiểm tra reflection/proxy/resource trong luồng thường dùng |
| Đường lỗi và validation | Kiểm tra nhánh ít được gọi |
| Serialization/JSON binding | Kiểm tra DTO và subtype cần thiết |
| Security/login | Kiểm tra metadata liên quan tới authentication |
| Plugin/strategy được chọn theo config | Kiểm tra các implementation hợp lệ |
| Resource/template/message bundle | Kiểm tra file tĩnh và resource bundle |
| Native integration test | Xác nhận hành vi trên executable thật |

Nếu native build thất bại với lỗi thiếu metadata hoặc runtime báo lỗi ở một nhánh cụ thể:

1. Xác định target class/member/resource bị thiếu.
2. Tìm entry tương ứng trong trace ban đầu.
3. Xem caller của entry có bị filter loại không.
4. Nếu caller là framework test nhưng luồng nghiệp vụ production cần access đó, tạo capture scenario production-like để giữ entry.
5. Thu metadata lại và chạy native test.

Một test JVM pass không đủ chứng minh filter an toàn. Bằng chứng cuối cùng phải đến từ native executable chạy các luồng production cần hỗ trợ.

## 12. Bài thực hành: loại metadata của JUnit và DevTools

Giả sử ứng dụng `billing-service` có:

- Package ứng dụng `com.example.billing`.
- Test helper `com.example.billing.testsupport`.
- JUnit 5, Mockito và AssertJ trong test scope.
- Spring Boot DevTools chỉ dùng khi phát triển.

Thực hiện:

1. Build executable JAR với runtime dependencies.
2. Xác nhận DevTools và test dependencies không nằm trong runtime classpath của lần capture.
3. Tạo `caller-filter.json` loại `org.junit.**`, `org.mockito.**`, `org.assertj.**`, `org.springframework.boot.devtools.**` và `com.example.billing.testsupport.**`.
4. Nếu trace có target chỉ thuộc test fixture, tạo `access-filter.json` loại đúng package fixture đó.
5. Chạy JAR bằng GraalVM JDK với `caller-filter-file`, `access-filter-file` và `config-output-dir`.
6. Gọi endpoint tạo đơn hàng, thanh toán, đăng nhập và các luồng có reflection/serialization.
7. Chạy capture bổ sung bằng `config-merge-dir` cho các nhánh còn thiếu.
8. Review metadata và xác minh không có package test/devtools không cần thiết.
9. Build native executable với metadata đã duyệt.
10. Chạy native integration test cho các luồng nghiệp vụ.
11. Thử bỏ một rule filter trong nhánh thử nghiệm để so sánh metadata; ghi lại entry nào thay đổi và lý do.

### Câu hỏi tự kiểm tra

1. Caller filter và access filter khác nhau ở đối tượng được so khớp như thế nào?
2. Vì sao loại caller `org.junit.**` thường phù hợp khi tracing test JVM?
3. Nếu JUnit gọi một test method, nhưng method đó gọi reflection của ứng dụng, caller của dynamic access có thể là class nào?
4. Vì sao không nên loại toàn bộ `net.bytebuddy.**` một cách mặc định?
5. Pattern `.*` và `.**` khác nhau ở phạm vi package như thế nào?
6. Vì sao thứ tự rule có thể làm một class được include lại sau khi bị exclude?
7. Khi nào nên dùng access filter để loại test fixture target?
8. Vì sao nên capture từ packaged application thay vì chỉ chạy test suite?
9. Làm thế nào phát hiện filter đã loại metadata cần cho một nhánh production?
10. Vì sao metadata nhiều hơn không đồng nghĩa native executable tốt hơn?

**Tiêu chí đạt:** giải thích được caller filter và access filter; viết được filter JSON có thứ tự rule rõ ràng; loại được truy cập chỉ do test framework/DevTools khởi phát mà không loại nhầm dynamic access của ứng dụng; thu metadata từ packaged application với các kịch bản production-like; review và merge metadata có kiểm soát; cuối cùng xác minh các luồng nghiệp vụ trên native executable.

## Tài liệu chính thức

- GraalVM — Collect Metadata with the Tracing Agent: https://www.graalvm.org/jdk25.5/reference-manual/native-image/metadata/AutomaticMetadataCollection/
- GraalVM — Native Image Tracing Agent (versioned documentation): https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/AutomaticMetadataCollection/
- GraalVM — Reachability Metadata and filter format: https://www.graalvm.org/jdk25/reference-manual/native-image/metadata/
