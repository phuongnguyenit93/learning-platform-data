
# Theo dõi và loại bỏ dần cờ mở quyền sau khi nâng cấp dependency

Trong quá trình chuyển đổi phiên bản Java, một ứng dụng cũ có thể cần các tùy chọn JVM như `--add-opens` và `--add-exports` để khởi động hoặc để một framework tiếp tục truy cập vào những package không được công khai theo quy tắc Java Platform Module System (JPMS). Những cờ này hữu ích như **biện pháp chuyển tiếp**, nhưng nếu được sao chép mãi qua các lần nâng cấp dependency, hệ thống sẽ dần tích lũy quyền truy cập không cần thiết, che khuất thư viện lỗi thời và khiến lần nâng cấp JDK tiếp theo khó kiểm soát.

Bài học này tập trung vào việc **lập danh mục, xác định nguyên nhân, kiểm chứng và loại bỏ có kiểm soát** các cờ mở quyền khi dependency đã được nâng cấp. Mục tiêu không phải xóa mọi cờ bằng mọi giá: một số ứng dụng hoặc framework thực sự cần quyền truy cập được khai báo có chủ đích. Mục tiêu là mỗi quyền còn lại phải có **lý do kỹ thuật, phạm vi tối thiểu, bằng chứng kiểm thử, chủ sở hữu và kế hoạch đánh giá lại**.

Nội dung nằm trong bối cảnh *Java Advance Compatibility Migration*, phần *Reflection và API nội bộ*.

## 1. Vì sao cờ mở quyền xuất hiện khi nâng cấp Java?

Trước hệ thống module, nhiều thư viện sử dụng reflection để gọi constructor, method hoặc đọc field không public. Một số thư viện còn tham chiếu trực tiếp đến API nội bộ JDK. Từ Java 9, JPMS đặt ra ranh giới rõ hơn giữa module và package; những ranh giới này được thực thi ngày càng chặt trong các bản JDK sau.

Ví dụ một framework cũ cố truy cập sâu vào `java.lang.String` bằng reflection:

~~~java
import java.lang.reflect.Field;

public final class LegacyInspector {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
~~~

Trên một số runtime mới, lệnh `setAccessible(true)` có thể thất bại với `java.lang.reflect.InaccessibleObjectException` do package `java.lang` của module `java.base` không được mở cho module của caller.

Một workaround thường gặp là:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

Cờ này mở package `java.lang` của `java.base` cho **deep reflection** từ các unnamed module. Nó không biến việc truy cập private implementation thành API ổn định, và cũng không bảo đảm code sẽ tiếp tục hoạt động nếu cấu trúc nội bộ thay đổi.

Nếu nâng framework lên phiên bản không còn truy cập field private đó, cờ mở có thể đã trở nên thừa. Khi ấy, giữ cờ sẽ không mang lại giá trị tương thích nhưng vẫn mở rộng phạm vi truy cập.

### 1.1. Cờ là dấu vết của vấn đề từng xảy ra

Một cờ có thể đã được thêm vì:

- Framework phiên bản cũ cố truy cập thành viên private trong JDK.
- Thư viện phụ thuộc JDK internal API.
- Serialization/ORM/proxy framework cần reflection tới package của ứng dụng.
- Java agent hoặc thư viện instrumentation chưa hỗ trợ JDK mới.
- Test framework cần quyền truy cập để tạo mock hoặc chạy test.
- Một dependency bắc cầu, plugin hoặc code generator kích hoạt lỗi.
- Người vận hành sao chép bộ JVM flags từ dự án khác mà chưa kiểm chứng.

Không phải mọi cờ xuất hiện trong hệ thống đều còn cần. Vì vậy, cần phân biệt **lý do lịch sử** với **nhu cầu hiện tại**.

### 1.2. Vì sao không nên xóa tất cả cùng lúc?

Nếu nhiều cờ được gỡ đồng thời và hệ thống lỗi, khó biết cờ nào liên quan đến module, code path hay dependency nào. Một cờ có thể chỉ cần khi chạy batch job, integration test hoặc khi kích hoạt một plugin ít dùng. Quy trình phù hợp là thu thập baseline, thử loại bỏ từng nhóm nhỏ, theo dõi và có phương án rollback.

## 2. Hiểu đúng ý nghĩa của từng loại cờ

Để loại bỏ chính xác, cần hiểu cờ đang cấp quyền gì.

| Cờ/cơ chế | Ý nghĩa chính | Tình huống thường gặp |
|---|---|---|
| `--add-opens` | Mở package của module nguồn cho deep reflection từ module đích ở runtime | Framework cần đọc/gọi thành viên non-public |
| `--add-exports` | Export package cho truy cập bình thường đến các kiểu public trong package theo quy tắc module | Mã biên dịch hoặc runtime tham chiếu API public nhưng package không được export |
| `--add-reads` | Bổ sung quan hệ module readability | Named module cần đọc module khác |
| `opens ... to ...` trong `module-info.java` | Module nguồn chủ động mở package cụ thể cho module đích | Ứng dụng modular chủ đích cho ORM/serializer truy cập |
| `open module ...` | Mở toàn bộ package của module cho reflection | Cần cân nhắc vì phạm vi lớn |
| `--illegal-access` | Cơ chế tương thích cũ trên một số release trước đây | Không nên tiếp tục dựa vào trên JDK 17+ |

### 2.1. Cú pháp của --add-opens

~~~text
--add-opens <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Ví dụ:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Trong ví dụ:

- `java.base` là module chứa package.
- `java.lang` là package được mở.
- `ALL-UNNAMED` chỉ các unnamed module, thường là code trên classpath.

Nếu consumer là **named module**, có thể sử dụng tên module đích thay vì mở cho mọi unnamed module:

~~~bash
java --add-opens java.base/java.lang=com.example.inspector --module-path mods \
  -m com.example.inspector/com.example.inspector.Main
~~~

Đây là ví dụ cú pháp. Module `com.example.inspector` và quyền truy cập thực tế cần được xác nhận trong hệ thống. Sử dụng module đích cụ thể có thể giảm phạm vi so với `ALL-UNNAMED`, nhưng không phải lúc nào code trên classpath cũng có thể thay bằng tên module.

### 2.2. Cú pháp của --add-exports

~~~text
--add-exports <source-module>/<package>=<target-module>(,<target-module>)*
~~~

Ví dụ minh họa:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -jar app.jar
~~~

Cờ này không tương đương với việc mở package để phản chiếu vào thành viên private. Nếu lỗi là `InaccessibleObjectException` khi gọi `setAccessible`, cần đánh giá điều kiện deep reflection, chứ không mặc định chuyển qua `--add-exports`.

Ngược lại, nếu lỗi là `IllegalAccessError` do truy cập tới lớp trong package không được export, thì chỉ thêm `--add-opens` không nhất thiết giải quyết đúng vấn đề về API access thông thường.

### 2.3. Cờ compile-time và runtime là hai phạm vi khác nhau

Một dependency có thể biên dịch được vì compiler được cấp `--add-exports` nhưng lại lỗi trên JVM khi chạy, hoặc ngược lại. Phải tách riêng:

- Các tham số của `javac`.
- Các JVM arguments chạy test.
- Các JVM arguments chạy ứng dụng hoặc task JavaExec.
- Các tham số mà container/launcher inject vào.
- Cấu hình agent và công cụ chạy bytecode.

`--add-opens` chủ yếu phục vụ runtime reflection. Không được xem một danh sách cờ trong Gradle compiler options là bằng chứng ứng dụng production cũng dùng các cờ tương tự.

### 2.4. Không dựa vào --illegal-access trên JDK mới

Trong giai đoạn chuyển tiếp của JPMS, một số release có `--illegal-access` để nới lỏng truy cập đến package JDK cũ. Trên JDK 17, cơ chế này không còn cung cấp cách mở rộng truy cập như trước; tùy chọn cũ có thể bị bỏ qua kèm cảnh báo. Quy trình migration phải giải quyết nguyên nhân hoặc dùng quyền mở **rõ ràng, có phạm vi** nếu thật sự cần.

Tuyệt đối không kết luận rằng “ứng dụng an toàn vì đã có `--illegal-access=permit`” khi chạy JDK hiện đại.

## 3. Vòng đời quản lý một cờ mở quyền

Một cờ nên được quản lý như một ngoại lệ kỹ thuật có vòng đời:

~~~mermaid
flowchart TD
    A["Phát hiện cờ trong cấu hình"] --> B["Ghi nhận owner và lý do"]
    B --> C["Xác định dependency / code path cần quyền"]
    C --> D["Nâng dependency hoặc thay implementation"]
    D --> E["Chạy thử không có cờ"]
    E --> F{"Các kiểm thử liên quan đạt?"}
    F -->|Có| G["Xóa khỏi mọi cấu hình liên quan"]
    F -->|Không| H["Thu thập lỗi, giới hạn phạm vi, lên kế hoạch sửa"]
    H --> C
    G --> I["Thêm guardrail và theo dõi release sau"]
~~~

Các trạng thái quản trị có thể dùng:

| Trạng thái | Ý nghĩa |
|---|---|
| DISCOVERED | Cờ được tìm thấy nhưng chưa xác minh nhu cầu |
| JUSTIFIED | Có bằng chứng runtime và chủ sở hữu |
| CANDIDATE | Dependency đã được nâng; cờ có khả năng không còn cần |
| TESTING | Đang thử chạy không có cờ trên các môi trường liên quan |
| REMOVED | Cờ đã được xóa và kiểm chứng |
| RETAINED | Vẫn cần; có nguyên nhân, giới hạn và ngày đánh giá lại |
| BLOCKED | Không thể xóa ngay vì vấn đề cụ thể đã được tái hiện |

Tên trạng thái chỉ là ví dụ, không phải tiêu chuẩn bắt buộc. Điều quan trọng là tránh trạng thái mơ hồ “đã từng cần nên giữ nguyên”.

## 4. Tạo baseline của toàn bộ cờ đang dùng

Trước khi thay đổi dependency hoặc xóa cờ, cần xây dựng một **inventory** có thể đối chiếu giữa các phiên bản và môi trường.

### 4.1. Không chỉ tìm trong một file startup

Các nguồn có thể chứa JVM flags:

- Script `run.sh`, `start.sh`, batch file, PowerShell script.
- Dockerfile, container entrypoint hoặc image startup configuration.
- Kubernetes Deployment/StatefulSet, Helm values, Kustomize overlay.
- CI pipeline và runner configuration.
- Gradle `Test`, `JavaExec`, `applicationDefaultJvmArgs`.
- Maven Surefire/Failsafe `argLine`.
- Application server hoặc service wrapper.
- Systemd service unit và các biến môi trường.
- IDE run configuration.
- Java agent installer hoặc bootstrap script.
- Biến môi trường như `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, hoặc `_JAVA_OPTIONS` khi runtime tương ứng hỗ trợ.
- Cấu hình của environment riêng: development, test, staging, production, batch worker và scheduled job.

Tìm kiếm bằng ripgrep trong repository:

~~~bash
rg -n --hidden --glob '!**/.git/**' -- \
  '--add-opens|--add-exports|--add-reads|--illegal-access' .
~~~

Tùy cách shell và phiên bản công cụ, có thể dùng nhiều mẫu tìm riêng nếu cần. Nếu một biến môi trường chỉ được đặt ngoài repository, tìm mã nguồn sẽ không tìm ra; cần kiểm tra cấu hình triển khai đã được phê duyệt.

### 4.2. Nhận diện cờ đang có hiệu lực tại runtime

Với JVM đang chạy và được phép chẩn đoán, có thể xem command line:

~~~bash
jcmd <pid> VM.command_line
~~~

Hoặc trong Java code khi phù hợp:

~~~java
import java.lang.management.ManagementFactory;

public final class VmArgs {
    public static void main(String[] args) {
        for (String arg :
                ManagementFactory.getRuntimeMXBean().getInputArguments()) {
            System.out.println(arg);
        }
    }
}
~~~

Cần thận trọng khi ghi log toàn bộ JVM arguments vì chúng có thể chứa bí mật hoặc thông tin nhạy cảm. Chỉ trích xuất các cờ cần kiểm tra; tránh đưa token, mật khẩu hay thông tin cấu hình bí mật vào ticket công khai.

Cờ có thể đi vào JVM qua nhiều kênh, nên kết quả chẩn đoán cần được đối chiếu với launcher và môi trường thực tế. Ghi luôn phiên bản JDK:

~~~bash
java -version
~~~

### 4.3. Chuẩn hóa định dạng inventory

Một mẫu bảng theo dõi:

| ID | Cờ chính xác | Môi trường | Nguyên nhân lịch sử | Dependency/call site | Owner | Trạng thái |
|---|---|---|---|---|---|---|
| OPEN-01 | `--add-opens java.base/java.lang=ALL-UNNAMED` | Test | Mock framework cũ | Mocking adapter | Test team | CANDIDATE |
| OPEN-02 | `--add-opens java.base/java.time=ALL-UNNAMED` | Production | Serializer dùng private field | JSON mapper | Backend team | JUSTIFIED |
| EXP-03 | `--add-exports java.base/sun.nio.ch=ALL-UNNAMED` | Batch | Native buffer utility | Legacy buffer lib | Platform team | BLOCKED |

Các dòng trên là **ví dụ minh họa**, không phải khuyến nghị nên thêm các cờ đó.

Mỗi dòng nên có thêm:

- Lý do được ghi nhận khi cờ xuất hiện.
- JDK và dependency version lúc phát sinh.
- Lỗi hoặc stack trace ban đầu.
- Module/package được mở.
- Target cụ thể hoặc `ALL-UNNAMED`.
- Những tiến trình thực sự dùng cờ.
- Phiên bản dependency dự kiến loại bỏ nhu cầu.
- Test bao phủ code path liên quan.
- Ngày kiểm tra gần nhất và mốc đánh giá tiếp theo.
- PR/ticket để truy vết thay đổi.

## 5. Chẩn đoán nguyên nhân: ai thực sự cần cờ?

Không nên quyết định giữ cờ chỉ bằng cảm giác rằng “thư viện X từng cần nó”. Cần xác định **consumer hiện tại**.

### 5.1. Đọc exception theo đúng loại

Ví dụ lỗi reflection:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make ... accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Từ lỗi, xác định:

1. Module nguồn là `java.base`.
2. Package bị truy cập là `java.lang`.
3. Consumer nằm trong unnamed module hoặc named module được chỉ rõ.
4. Dấu vết stack trace cho biết framework/dependency nào gọi reflection.
5. Code path nào kích hoạt lời gọi.

Nếu thông báo là:

~~~text
java.lang.IllegalAccessError:
class ... cannot access class ... because module ...
does not export ... to ...
~~~

đây thường là vấn đề **module export/access**, khác với deep reflection. Cần tìm code dùng API không export và xem thư viện có bản thay thế sử dụng API công khai chưa.

Một số lỗi liên quan khác:

| Lỗi/triệu chứng | Câu hỏi nên kiểm tra |
|---|---|
| `InaccessibleObjectException` | Package có cần mở cho deep reflection không? Caller nào đang truy cập? |
| `IllegalAccessException` | Reflection access checks, visibility và module boundary có phù hợp? |
| `IllegalAccessError` | Bytecode đang truy cập member hoặc package không được phép? |
| `NoClassDefFoundError` | Class hoặc dependency có bị thiếu, tách module hoặc không load được? |
| `NoSuchMethodError` | Binary incompatibility của dependency, không nhất thiết là thiếu `--add-opens` |
| `UnsupportedClassVersionError` | Bytecode cần JVM mới hơn, không thể sửa bằng cờ opens |
| Framework không scan được class | Annotation metadata/visibility, classpath hoặc module openness có đúng? |

**Không dùng `--add-opens` làm lời giải chung cho mọi lỗi sau nâng cấp Java.**

### 5.2. Xác định component từ stack trace

Thực hiện theo thứ tự:

- Lấy stack trace đầy đủ từ môi trường có thể tái hiện.
- Xác định frame đầu tiên thuộc thư viện ứng dụng hoặc framework liên quan.
- Kiểm tra dependency version đang được resolve.
- Tra release note hoặc migration guide của phiên bản mới.
- Kiểm tra classpath để tránh có hai phiên bản thư viện.
- Xác minh path lỗi vẫn tồn tại sau khi đã nâng dependency.

Khi dùng reflection, lỗi có thể bắt nguồn từ một helper rất sâu trong dependency bắc cầu. Cần truy ra module sở hữu việc truy cập, không chỉ module gọi phương thức nghiệp vụ phía ngoài.

### 5.3. Phân tích dependency tĩnh bằng jdeps

`jdeps` giúp tìm những tham chiếu tĩnh tới JDK internal API:

~~~bash
jdeps --jdk-internals --recursive path/to/library.jar
~~~

Có thể phân tích cùng classpath phù hợp:

~~~bash
jdeps --jdk-internals --recursive --class-path "lib/*" app.jar
~~~

Nhưng cần nhớ:

- `jdeps` không chứng minh cờ `--add-opens` còn cần.
- Reflection dùng tên class động hoặc chuỗi có thể không hiện ở kết quả tĩnh.
- Một số dependency nằm trong nested JAR cần được trích xuất hoặc phân tích riêng.
- Phân tích phải chạy trên đúng artifact và dependency version.
- Một tham chiếu internal API không nhất thiết đồng nghĩa với deep reflection; cần phân biệt `--add-exports` và `--add-opens`.

Phân tích tĩnh giúp tìm đối tượng điều tra; **kiểm thử runtime khi bỏ cờ** mới là bằng chứng trực tiếp cho một code path cụ thể.

## 6. Nâng dependency trước khi gỡ cờ

Cách giảm cờ bền vững nhất là nâng dependency lên phiên bản dùng API public hoặc cơ chế module phù hợp. Chỉ xóa cờ mà giữ thư viện cũ có thể khiến một chức năng ít dùng hỏng ở production.

### 6.1. Xác định dependency thực sự được nạp

Trong Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency byte-buddy \
  --configuration runtimeClasspath
~~~

Trong Maven:

~~~bash
mvn dependency:tree
~~~

Các lệnh là ví dụ để người học thực hiện trên dự án của họ; không bắt buộc áp dụng mọi lệnh cho mọi build.

Cần lưu lại:

- Dependency trực tiếp, dependency bắc cầu.
- Version thực tế, không chỉ version khai báo.
- Dependency management, BOM và forced resolution.
- Plugin hoặc agent có bộ dependency riêng.
- Những module chỉ có trong testRuntimeClasspath.
- JAR được nạp bằng custom class loader.

### 6.2. Đọc release notes theo đúng JDK mục tiêu

Ví dụ framework serialization hoặc mocking có thể nâng cấp cách thao tác reflection, sử dụng method handle hoặc thay đổi chiến lược truy cập. Tuy nhiên, việc phiên bản mới “hỗ trợ JDK 21” không tự chứng minh đã bỏ được mọi cờ. Nhà cung cấp có thể vẫn yêu cầu mở một package vì thiết kế chính thức của framework.

Kiểm tra tài liệu:

- JDK tối thiểu và JDK được kiểm thử.
- Những thay đổi trong reflection/module access.
- Yêu cầu về agent, bytecode generation hoặc native integration.
- Release note về loại bỏ illegal reflective access.
- Cấu hình mới thay thế một cờ cũ.
- Breaking change của serializer/ORM nếu nâng major version.

Một dependency nâng cấp có thể giải quyết lỗi truy cập nhưng đồng thời thay đổi format JSON, proxy behavior hoặc dữ liệu. Phải chạy regression test của phần nghiệp vụ liên quan, không chỉ thử startup.

### 6.3. Không nhầm yêu cầu mở package của ứng dụng với mở JDK

Có hai nhóm khác nhau:

**Nhóm A — mở package JDK**:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Thường xuất phát từ truy cập nội bộ JDK. Mục tiêu lâu dài là dùng thư viện/API không cần deep reflection vào implementation của JDK.

**Nhóm B — mở package do ứng dụng tự sở hữu**:

~~~text
--add-opens com.example.app/com.example.domain=com.fasterxml.jackson.databind
~~~

Nếu ứng dụng dùng named module và serializer cần reflection vào field/constructor của domain object, có thể chủ động khai báo `opens` có phạm vi trong `module-info.java`:

~~~java
module com.example.app {
    requires com.fasterxml.jackson.databind;
    opens com.example.domain to com.fasterxml.jackson.databind;
}
~~~

Đây là một thiết kế khác: ứng dụng **sở hữu package** và quyết định mở cho một framework cụ thể. Không nên cố loại bỏ bằng mọi giá nếu đó là cơ chế truy cập hợp lệ, nhưng vẫn nên chọn cách tối thiểu và ghi vào hợp đồng module.

Lưu ý: tên module và khả năng tương thích của từng thư viện phải xác minh với phiên bản thực tế. Không phải mọi thư viện đều là named module hoặc cần quyền truy cập như nhau.

## 7. Quy trình thử loại bỏ từng cờ sau nâng dependency

### Bước 1: Khóa baseline

Trước khi thay đổi:

- Ghi JDK vendor, version và bản cập nhật.
- Ghi checksum của artifact và phiên bản dependency.
- Ghi toàn bộ cờ đang có hiệu lực.
- Lưu smoke/integration test baseline.
- Ghi thời điểm và môi trường chạy.
- Xác định các chức năng có thể kích hoạt reflection và agent.

Một kết quả “PASS” không đáng tin nếu lần chạy trước và sau dùng hai artifact hoặc hai bộ dependency khác nhau mà không ghi nhận.

### Bước 2: Chọn một cờ ứng viên

Ưu tiên cờ có bằng chứng rõ:

- Chỉ được thêm để hỗ trợ dependency vừa nâng.
- Không có code ứng dụng nào trực tiếp dùng internal API tương ứng.
- Không còn stack trace cùng lỗi trên bản mới.
- Test có thể kích hoạt code path liên quan.
- Cờ chỉ nằm trong một tiến trình ít phụ thuộc, dễ rollback.

Nếu cờ trùng lặp ở nhiều nguồn cấu hình, phải xử lý việc **còn xuất hiện ở nguồn khác**; xóa một dòng khỏi file startup chưa chứng minh runtime không còn cờ.

### Bước 3: Loại bỏ cờ trong môi trường thử nghiệm

Ví dụ trước:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  --add-opens java.base/java.time=ALL-UNNAMED \
  -jar app.jar
~~~

Giả sử đã xác minh dependency mới không còn truy cập sâu vào `java.time`. Có thể thử:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -jar app.jar
~~~

Không nên thay đổi đồng thời cờ thứ hai, dependency version và cấu hình module nếu mục tiêu là xác định tác động riêng của một cờ.

### Bước 4: Chạy test kích hoạt code path

Bao gồm:

- Startup và dependency injection initialization.
- Serialization/deserialization của kiểu dữ liệu có custom field/constructor.
- ORM entity scanning và query mapping.
- Reflection vào private member hoặc annotation.
- Proxy, mocking, bytecode generation.
- Java agent startup, instrumentation hoặc dynamic attach.
- Plugin nạp động và service discovery.
- Scheduled job, batch flow và đường chạy ít sử dụng.
- Test trong container image/JDK được triển khai.

Test thiếu code path không chứng minh cờ không còn cần.

### Bước 5: Theo dõi lỗi và hành vi

Thu thập exception, log, cảnh báo JVM, error rate, trace và metric nghiệp vụ. Không chỉ tìm chuỗi `InaccessibleObjectException`; một serializer có thể im lặng bỏ field và trả về dữ liệu thiếu, hoặc một framework có thể fallback sang đường thực thi khác gây giảm hiệu năng.

Một số dấu hiệu cần chú ý:

- API trả kết quả thiếu field hoặc sai format.
- Bean/handler không được đăng ký.
- ORM mapping đổi hành vi.
- Test mock/proxy không tạo được.
- Agent không instrument class như mong đợi.
- Exception chỉ xuất hiện ở lần xử lý đầu tiên.
- Timeouts, retries hoặc CPU overhead mới xuất hiện.

### Bước 6: Kết luận theo phạm vi đã thử

Nếu test đạt, không nên ghi “cờ chắc chắn vô dụng trong mọi trường hợp”. Ghi nhận:

- Cờ được bỏ.
- Phiên bản dependency/JDK của lần thử.
- Những test/code path đã chạy.
- Những cấu hình/môi trường chưa thử.
- Quan sát trong staging/canary.
- Cơ chế rollback.

Nếu test thất bại, giữ cờ tạm thời, ghi lỗi và quay lại điều tra nguyên nhân. Tránh mở thêm một loạt package mới để né triệu chứng khi chưa hiểu dependency.

### Bước 7: Gỡ khỏi mọi nơi và thêm guardrail

Sau khi đủ bằng chứng:

- Xóa khỏi source cấu hình gốc.
- Xóa bản sao trong CI, staging, production, test launcher hoặc service wrapper.
- Kiểm tra startup arguments thực tế sau deploy.
- Cập nhật tài liệu kỹ thuật và inventory.
- Thêm kiểm tra tránh cờ cũ tự quay lại.
- Theo dõi sau rollout theo mốc đã thống nhất.

## 8. Ví dụ về kiểm soát trong Gradle, Maven và môi trường triển khai

### 8.1. Gradle Test task

Một cấu hình test cũ:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'java.base/java.lang=ALL-UNNAMED'
    )
}
~~~

Nếu framework test mới không còn cần quyền này, bỏ đối số trong `Test` task, sau đó chạy chính suite có mock/reflection liên quan.

Nếu `test` và `integrationTest` là hai task khác nhau, phải kiểm tra cả hai task. Việc loại cờ khỏi `test` không có nghĩa `integrationTest` đã sạch.

Không thay vì cờ rõ ràng bằng cách mở rộng quyền trên toàn bộ JavaExec/worker nếu chỉ một task cần. Phạm vi cờ nên nhỏ nhất có thể.

### 8.2. Gradle JavaExec và ứng dụng

Ví dụ:

~~~groovy
tasks.named('run', JavaExec) {
    jvmArgs '--add-opens=java.base/java.lang=ALL-UNNAMED'
}
~~~

Với Gradle Application Plugin còn có thể gặp:

~~~groovy
application {
    applicationDefaultJvmArgs = [
        '--add-opens=java.base/java.lang=ALL-UNNAMED'
    ]
}
~~~

Các ví dụ trên mô tả vị trí có thể chứa cờ, **không phải khuyến nghị thêm cờ**. Khi loại bỏ, cần kiểm tra startup script được tạo từ application plugin hoặc bản phân phối đã đóng gói.

### 8.3. Maven Surefire và Failsafe

Một dự án cũ có thể khai báo:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <configuration>
    <argLine>--add-opens java.base/java.lang=ALL-UNNAMED</argLine>
  </configuration>
</plugin>
~~~

Nếu dự án có Failsafe cho integration test, cấu hình của Failsafe có thể khác. Ngoài ra, JaCoCo hoặc plugin khác có thể bổ sung `argLine` theo cách riêng. Khi sửa, cần bảo đảm không vô tình loại agent hoặc JVM flag không liên quan; thay đổi chỉ cờ đã được chứng minh thừa.

### 8.4. Container và Kubernetes

Ví dụ startup container dùng `JDK_JAVA_OPTIONS`:

~~~bash
export JDK_JAVA_OPTIONS="--add-opens=java.base/java.lang=ALL-UNNAMED"
java -jar app.jar
~~~

Một Helm chart có thể cung cấp cùng cờ ở giá trị cấu hình của nhiều môi trường. Nếu chỉ xóa dòng trong Dockerfile nhưng deployment inject lại cờ, runtime thực tế vẫn mở package đó.

Sau deploy, xác nhận thông số runtime của đúng pod/instance và đúng phiên bản JDK, tránh kết luận dựa trên manifest chưa được rollout.

### 8.5. Kiểm tra tự động sau khi đã có allowlist

Có thể dùng kiểm tra giản lược trong CI để phát hiện cờ mới bị thêm không có chủ sở hữu:

~~~bash
rg -n -- '--add-opens|--add-exports' \
  deploy scripts build.gradle settings.gradle pom.xml
~~~

Trong thực tế, một guardrail hữu ích nên:

1. Quét các file cấu hình đã biết.
2. So sánh với danh sách ngoại lệ được duyệt.
3. Yêu cầu ghi ID ticket, owner và lý do với quyền mới.
4. Báo lỗi khi xuất hiện cờ ngoài allowlist.
5. Có cơ chế duyệt thay đổi allowlist.

Không nên tự động chặn mọi occurrence trong README hoặc test fixture chứa ví dụ về cờ; phạm vi quét phải phù hợp.

## 9. Thu hẹp quyền nếu chưa thể loại bỏ hoàn toàn

Có những trường hợp dependency mới vẫn cần một quyền mở. Khi đó, có thể cải thiện cấu hình theo hướng **ít quyền nhất** thay vì giữ nguyên tất cả quyền cũ.

### 9.1. Thu hẹp module đích

Nếu một library chạy dưới named module và đã xác nhận module tên `com.example.framework`, cân nhắc thay:

~~~text
--add-opens com.example.app/com.example.domain=ALL-UNNAMED
~~~

bằng:

~~~text
--add-opens com.example.app/com.example.domain=com.example.framework
~~~

Nhưng chỉ khi framework thực sự chạy trong named module đó. Nếu nó nằm trên classpath, target `ALL-UNNAMED` vẫn có thể cần; thay thành tên không phù hợp sẽ khiến nó mất quyền.

### 9.2. Chuyển thành opens trong module-info khi sở hữu package

Với code modular của ứng dụng, một directive:

~~~java
opens com.example.domain to com.example.framework;
~~~

có thể thể hiện ý định rõ ràng hơn một startup flag rải rác. Điều này không áp dụng cho package của JDK mà ứng dụng không sở hữu.

Không cần mở cả module nếu framework chỉ cần một package; hãy tránh `open module` khi mục tiêu là giới hạn quyền.

### 9.3. Thay reflection không cần thiết bằng API công khai

Nếu ứng dụng tự dùng reflection để lấy dữ liệu từ một class JDK private, hãy cân nhắc API public thay thế, adapter hoặc thiết kế khác.

Ví dụ, không truy cập internal encoder/decoder chỉ vì thư viện cũ làm vậy; đối với Base64 thông thường, Java SE có API public:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class Encoder {
    public static String encode(String value) {
        byte[] input = value.getBytes(StandardCharsets.UTF_8);
        return Base64.getEncoder().encodeToString(input);
    }
}
~~~

Không nên giả định `MethodHandles.privateLookupIn` là cách “vượt” JPMS: nó vẫn tuân thủ quy tắc module access và có thể yêu cầu package được mở phù hợp. Mục tiêu là tránh truy cập private implementation khi không thực sự cần, không chỉ đổi cú pháp.

### 9.4. Cờ có thể là nhu cầu thiết kế có chủ đích

Một số framework được thiết kế để truy cập domain model bằng reflection, và ứng dụng chấp nhận điều đó. Với package do ứng dụng sở hữu, giải pháp có thể là module `opens` đúng phạm vi; với một agent hay công cụ instrumentation, cấu hình đặc biệt có thể là phần được tài liệu hóa.

Khi chưa thể gỡ:

- Giữ phạm vi package và target nhỏ nhất có thể.
- Không che giấu cờ trong biến môi trường khó truy vết.
- Ghi lý do, owner và deadline đánh giá lại.
- Theo dõi bản dependency mới và policy JDK.
- Test riêng quyền đó trong CI.

## 10. Theo dõi tác động bảo mật và vận hành

Cờ mở quyền làm giảm mức đóng gói của module trong phạm vi được chỉ định. Chúng không tự động trao mọi đặc quyền hệ điều hành, nhưng có thể cho phép code được cấp quyền truy cập sâu vào implementation hoặc các member mà JPMS bình thường ngăn cản.

Điều này tạo ra một số rủi ro:

- **Rủi ro phụ thuộc implementation:** code tiếp tục sử dụng field/method nội bộ có thể đổi giữa JDK.
- **Rủi ro bảo trì:** rất khó biết cờ nào còn hữu ích khi không có tài liệu.
- **Rủi ro phạm vi:** `ALL-UNNAMED` áp dụng cho nhiều thành phần trên classpath hơn chỉ một thư viện.
- **Rủi ro phát hành:** cờ bị bỏ qua/không phù hợp trên một phiên bản Java có thể làm hành vi thay đổi.
- **Rủi ro vận hành:** cờ ở production khác test khiến kết quả kiểm chứng mất ý nghĩa.
- **Rủi ro quan sát:** framework có thể fallback âm thầm khi không thể phản chiếu.

Cần cân bằng rủi ro khi **giữ cờ không cần thiết** với rủi ro khi **xóa quá sớm**. Đề xuất thực tế là loại bỏ dựa trên bằng chứng từng quyền thay vì quyết định thuần hình thức.

## 11. Ví dụ migration từng giai đoạn

Giả sử ứng dụng chạy trên Java 17 có ba cờ trong startup:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/java.time=ALL-UNNAMED
--add-exports java.base/sun.nio.ch=ALL-UNNAMED
~~~

Qua điều tra ban đầu:

| ID | Lý do ban đầu | Thay đổi dependency | Hướng xử lý |
|---|---|---|---|
| A | Test mocking cũ truy cập private JDK | Mocking/bytecode library được nâng | Thử gỡ cờ `java.lang` khỏi test trước |
| B | JSON mapper cũ reflection vào `java.time` | Mapper được nâng để dùng public API | Thử gỡ cờ `java.time` trong staging |
| C | Buffer library dùng internal `sun.nio.ch` | Chưa có bản thay thế | Giữ tạm, đánh giá API công khai và phụ thuộc |

**Giai đoạn 1 — Inventory:** chụp JVM arguments của test, staging và production. Ghi checksum artifact và dependency versions.

**Giai đoạn 2 — Nâng dependency:** thử đúng thư viện mới trong môi trường kiểm thử, chạy regression test. Giữ cờ trước để tách vấn đề nâng dependency khỏi vấn đề thu hồi quyền.

**Giai đoạn 3 — Gỡ A:** bỏ cờ khỏi test task, chạy test mock/proxy có liên quan; nếu đạt, ghi trạng thái REMOVED đối với test. Kiểm tra không có bản sao ở task khác.

**Giai đoạn 4 — Gỡ B:** chạy staging không có cờ `java.time`, thử serialization/deserialization nhiều kiểu ngày giờ, timezone và format dữ liệu cũ. Theo dõi error rate trước khi triển khai production.

**Giai đoạn 5 — Đánh giá C:** vì `--add-exports` có mục đích khác `--add-opens`, không thay nó bằng một cờ opens bừa bãi. Ưu tiên nâng/thay buffer library, hoặc kiểm tra tính cần thiết thực sự bằng phân tích bytecode và runtime.

**Giai đoạn 6 — Guardrail:** cập nhật allowlist: A và B bị loại bỏ; C còn lại với owner, ticket, phạm vi và mốc đánh giá.

Bảng chỉ minh họa một tình huống thường gặp. Không được coi đây là bằng chứng rằng một phiên bản framework cụ thể sẽ hoặc sẽ không cần cờ.

## 12. Phát hiện cờ quay trở lại sau nâng cấp

Cờ có thể tái xuất hiện do:

- Copy cấu hình từ nhánh cũ.
- Docker image/Helm values chưa được đồng bộ.
- Một dependency khác vẫn yêu cầu cùng quyền.
- Plugin test bổ sung cờ bằng code.
- Build script sinh startup script từ một template cũ.
- Một engineer thêm workaround theo hướng dẫn lỗi thời.
- Lần nâng JDK tiếp theo xuất hiện vấn đề mới nhưng được giải quyết bằng cách mở rộng nhiều package.

Để phòng ngừa:

1. Quản lý inventory và allowlist trong version control.
2. Bắt buộc review khi thêm cờ mới.
3. Ghi lý do chính xác theo module/package/target.
4. Liên kết mỗi quyền với phiên bản dependency và test liên quan.
5. So sánh JVM arguments thực tế của staging và production với baseline.
6. Kiểm tra lại các ngoại lệ khi nâng JDK hoặc dependency.
7. Có chính sách xóa cờ không còn được dùng.

Một báo cáo “số cờ giảm từ 7 xuống 2” hữu ích nhưng chưa đủ. Cần quan tâm **phạm vi mở**, vì một cờ với `ALL-UNNAMED` có thể rộng hơn nhiều cờ chỉ mở package cho named module cụ thể.

## 13. Những sai lầm thường gặp

### 13.1. Gỡ cờ rồi chỉ thử startup

Nhiều lỗi reflection chỉ xuất hiện khi serialize một model đặc biệt, khởi tạo proxy hoặc chạy batch job. Startup đạt không chứng minh mọi đường chạy đạt.

### 13.2. Nâng dependency nhưng không kiểm tra version được resolve

Một BOM hoặc forced dependency có thể kéo về phiên bản cũ. Hãy đọc dependency graph thực tế thay vì chỉ nhìn khai báo trong build file.

### 13.3. Chỉ sửa cờ ở IDE

IDE configuration khác test task, container và production launcher. Thay đổi ở một nơi có thể không ảnh hưởng nơi khác.

### 13.4. Dùng --add-exports để chữa mọi lỗi reflection

`--add-exports` phục vụ API access bình thường tới package; `--add-opens` phục vụ deep reflection. Lỗi phải được phân loại trước.

### 13.5. Dùng --illegal-access làm giải pháp lâu dài

Tùy chọn tương thích cũ không còn đáp ứng kỳ vọng trên JDK mới. Không được dựa vào nó để chứng minh tương thích Java 17 trở lên.

### 13.6. Xóa cờ không cần thiết nhưng quên cập nhật allowlist

Nếu tài liệu và guardrail vẫn chứa cờ cũ, lần phát hành sau nó có thể bị thêm trở lại.

### 13.7. Thêm cờ theo stack trace mà không truy nguồn

Một lỗi về thiếu method, class file version hoặc serialization schema không nhất thiết do module access. Workaround không đúng có thể che giấu vấn đề cần sửa.

### 13.8. Giả định reflection vào package của ứng dụng cũng luôn xấu

Một framework có thể cần truy cập sâu vào domain model theo thiết kế. Khi package do ứng dụng sở hữu, mở package có phạm vi trong module descriptor có thể là lựa chọn hợp lệ. Mục tiêu là **quyền có chủ đích và tối thiểu**, không phải cấm toàn bộ reflection.

### 13.9. Không gắn kết quả thử với artifact và JDK cụ thể

Cùng một cờ có thể cần trên JDK/agent/dependency version khác nhau. Một kết luận từ local không thể chuyển thành cam kết production nếu môi trường hoặc artifact không giống nhau.

## 14. Mẫu hồ sơ ngoại lệ

Có thể ghi mỗi cờ bằng mẫu ngắn:

~~~yaml
id: OPEN-017
option: "--add-opens=java.base/java.lang=ALL-UNNAMED"
applies_to:
  - integration-test
source_module: java.base
package: java.lang
target: ALL-UNNAMED
reason: "Legacy test mocking library accesses JDK implementation via reflection"
owner: "Test Platform"
introduced_with: "Migration from older Java runtime"
dependency_to_upgrade: "Mocking / bytecode instrumentation stack"
evidence:
  - "Stack trace captured before dependency upgrade"
  - "Integration test suite exercising dynamic proxies"
status: TESTING
removal_criteria:
  - "Same artifact passes targeted tests without this option"
  - "Runtime arguments verified after deployment"
review_at: "Next dependency refresh"
~~~

Đây là YAML mẫu phục vụ quản lý nội bộ; không chứa bí mật. Tên trường và trạng thái có thể tùy chỉnh. Quan trọng là mỗi ngoại lệ trả lời được ba câu hỏi: **vì sao cần, ai chịu trách nhiệm và khi nào được bỏ**.

## 15. Checklist loại bỏ cờ mở quyền

### Kiểm kê

- [ ] Đã tìm `--add-opens`, `--add-exports`, `--add-reads` và các tùy chọn cũ liên quan.
- [ ] Đã rà soát build, test, CI, Docker, Kubernetes, service wrapper và môi trường.
- [ ] Đã xác nhận cờ đang có hiệu lực trên JVM thực tế.
- [ ] Đã ghi rõ source module, package, target module và owner.
- [ ] Đã phân biệt JDK internal package với package do ứng dụng sở hữu.

### Điều tra và nâng dependency

- [ ] Đã có stack trace, log hoặc bằng chứng thực tế cho quyền đang xét.
- [ ] Đã xác định dependency/module/call site cần quyền.
- [ ] Đã kiểm tra dependency graph và phiên bản được resolve.
- [ ] Đã đọc migration guide/release notes của dependency mới.
- [ ] Đã phân biệt deep reflection với access vào non-exported package.
- [ ] Đã xem xét API public hoặc thiết kế thay thế khi cần.

### Thử loại bỏ

- [ ] Đã lưu baseline artifact, JVM version, flags và kết quả test.
- [ ] Đã bỏ từng cờ hoặc từng nhóm nhỏ để dễ quy nguyên nhân.
- [ ] Đã chạy test kích hoạt reflection, serialization, ORM, proxy, agent và plugin liên quan.
- [ ] Đã chạy trên JDK và môi trường triển khai mục tiêu.
- [ ] Đã kiểm tra lỗi runtime và thay đổi hành vi không phát exception.
- [ ] Đã ghi rõ code path chưa được bao phủ và kế hoạch rollout.
- [ ] Đã chuẩn bị rollback nếu lỗi xuất hiện.

### Hoàn tất

- [ ] Đã xóa cờ khỏi mọi nơi khai báo thuộc phạm vi migration.
- [ ] Đã xác minh JVM arguments thực tế sau deploy.
- [ ] Đã cập nhật inventory, tài liệu và ticket.
- [ ] Đã thêm guardrail tránh cờ không được phê duyệt quay lại.
- [ ] Cờ còn giữ có chủ sở hữu, phạm vi tối thiểu và lịch đánh giá lại.
- [ ] Đã tách công việc loại bỏ cờ khỏi bước QA/publish nội dung đào tạo.

## Kết luận

Sau khi nâng cấp dependency, các cờ như `--add-opens` và `--add-exports` cần được **đánh giá lại có hệ thống**, không giữ theo thói quen và cũng không xóa hàng loạt thiếu kiểm chứng. Phải hiểu rõ cờ đang mở package nào cho module nào, dependency nào cần quyền, và code path nào có thể bị ảnh hưởng.

Một quy trình bền vững gồm **kiểm kê → truy nguyên nguyên nhân → nâng dependency → thử gỡ từng cờ → kiểm thử runtime → thu hồi khỏi mọi cấu hình → bảo vệ bằng guardrail**. Cờ còn lại là ngoại lệ có chứng cứ và chủ sở hữu; cờ đã bỏ được xác nhận bằng artifact và môi trường cụ thể. Cách quản lý này giúp tăng khả năng tương thích lâu dài, giảm phụ thuộc API nội bộ và làm những lần migration Java tiếp theo dễ dự đoán hơn.

