# Tích hợp một dependency có metadata từ repository hoặc hints của ứng dụng

## 1. Mục tiêu thực hành

Bài thực hành tích hợp một thư viện bên thứ ba có thao tác động, kiểm tra xem thư viện đã cung cấp GraalVM reachability metadata hay chưa, sau đó build và chạy Spring Boot Native Image. Nếu metadata upstream chưa bao phủ thao tác ứng dụng sử dụng, ta bổ sung Spring AOT RuntimeHints ở application module.

Cần phân biệt hai nguồn metadata:

- Metadata đi cùng dependency: do vendor/thư viện duy trì, thường được đóng gói trong JAR hoặc cung cấp qua GraalVM Reachability Metadata Repository.
- Hints của ứng dụng: do application khai báo cho cách nó sử dụng dependency, thường thông qua RuntimeHintsRegistrar.

Các tọa độ thư viện bên dưới là placeholder minh họa, không phải dependency có thật để copy nguyên trạng. Thay bằng thư viện thực tế của project và kiểm tra tài liệu/version của vendor.

## 2. Tình huống: thư viện tạo formatter bằng reflection

Giả sử service dùng thư viện xử lý tài liệu với API:

```java
DocumentFormatter formatter =
    DocumentEngine.createFormatter("com.vendor.docs.PdfFormatter");
byte[] output = formatter.format(input);
```

Ứng dụng gọi API công khai, nhưng thư viện nội bộ tìm class theo tên và gọi constructor qua reflection. Trên JVM, classpath đầy đủ thường cho phép thao tác này. Trong Native Image, class/member được truy cập động cần reachability metadata thích hợp.

Không thêm reflection hint ngay khi thấy API có tên class. Trước hết kiểm tra dependency đã có metadata built-in hay chưa.

## 3. Thêm dependency vào đúng application module

Gradle:

```groovy
dependencies {
    implementation("com.vendor:document-engine:2.4.0")
}
```

Maven:

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>document-engine</artifactId>
    <version>2.4.0</version>
</dependency>
```

Các giá trị group, artifact và version là placeholder. Thay bằng tọa độ vendor công bố. Dependency phải nằm trong runtime classpath của application module, không chỉ ở test scope hoặc module tooling.

Kiểm tra dependency đã resolve:

```bash
./gradlew :api-app:dependencyInsight --dependency document-engine --configuration runtimeClasspath
```

Hoặc Maven:

```bash
./mvnw -pl api-app dependency:tree
```

Ghi lại version thực tế, transitive dependencies và module sở hữu dependency. Nếu thư viện có nhiều artifact, xác định metadata được gộp trong JAR chính hay phát hành riêng.

## 4. Kiểm tra metadata trong JAR

Reachability metadata có thể nằm trong JAR theo convention của GraalVM, thường dưới META-INF/native-image/. Các phiên bản mới hỗ trợ định dạng hợp nhất reachability-metadata.json; thư viện cũ có thể dùng file riêng cho reflection, resources, proxies hoặc JNI.

Liệt kê nội dung JAR:

```bash
jar tf document-engine-2.4.0.jar | grep META-INF/native-image
```

Nếu dependency nằm trong Gradle cache hoặc Maven local repository, kiểm tra đúng JAR đã resolve. Không kiểm tra một JAR tải thủ công có version khác với version build đang dùng.

Một số thư viện cung cấp metadata qua GraalVM Reachability Metadata Repository thay vì đóng gói trong JAR. Native Build Tools/GraalVM có thể tra cứu theo tọa độ artifact/version tùy cấu hình và toolchain. Đọc tài liệu của plugin version đang dùng để xác nhận repository được hỗ trợ, bật đúng cách và metadata thực sự được nạp.

## 5. Đọc metadata và xác định phạm vi

Một file metadata hợp nhất có thể mô tả reflection, resources, serialization, JNI và proxies. Ví dụ minh họa:

```json
{
  "reflection": [
    {
      "type": "com.vendor.docs.PdfFormatter",
      "allDeclaredConstructors": true
    }
  ]
}
```

Đây là ví dụ khái niệm; schema và trường được hỗ trợ phụ thuộc GraalVM metadata version. Không tự tạo file với field không được schema hiện hành chấp nhận.

Khi review metadata, hãy hỏi:

- Type nào được đăng ký?
- Constructor, method hoặc field nào cần truy cập?
- Có đăng ký toàn bộ member không?
- Resource pattern có quá rộng không?
- Metadata có điều kiện theo class/feature không?
- Metadata áp dụng đúng version thư viện không?

Metadata quá rộng có thể làm tăng code/metadata được giữ lại. Metadata quá hẹp có thể khiến một nhánh runtime fail.

## 6. Xác minh metadata repository được sử dụng

Nếu metadata đến từ repository thay vì JAR, kiểm tra:

1. Tọa độ dependency và version đã resolve.
2. Native Build Tools/GraalVM version hỗ trợ cơ chế repository tương ứng.
3. Repository configuration được bật theo hướng dẫn plugin.
4. Build log cho biết metadata được tìm thấy/nạp.
5. Native Image build inputs chứa metadata mong đợi.
6. Regression test xác nhận thao tác động hoạt động.

Không giả định chỉ cần thêm dependency là metadata repository tự động được tải trong mọi cấu hình. Cách tích hợp phụ thuộc GraalVM Native Image và Native Build Tools version.

Nếu repository không có entry cho version dependency hoặc metadata không được resolve, hỏi vendor hoặc bổ sung hints ở ứng dụng sau khi xác định chính xác yêu cầu.

## 7. Viết integration test trước khi bổ sung hints

Tạo test gọi API thực tế của thư viện:

```java
@SpringBootTest
class DocumentFormattingTest {

    @Autowired
    DocumentService documentService;

    @Test
    void formatsPdfDocument() {
        byte[] result = documentService.format(sampleDocument());
        assertThat(result).isNotEmpty();
        assertThat(result).startsWith("%PDF");
    }
}
```

Đây là ví dụ minh họa; assertion phải phù hợp output format thật. Fixture nên nhỏ, xác định và không phụ thuộc dữ liệu bên ngoài không kiểm soát.

Chạy JVM test:

```bash
./gradlew :api-app:test
```

JVM pass chứng minh feature hoạt động trên JVM. Nó chưa chứng minh Native Image metadata đầy đủ.

## 8. Build native để xác minh metadata

Chạy native compilation bằng task/goal được project cấu hình. Ví dụ Gradle:

```bash
./gradlew :api-app:clean :api-app:nativeCompile
```

Task có thể khác tùy Spring Boot plugin và Native Build Tools version. Xem task list và build log. Với Maven, dùng Spring Boot Maven Plugin/Native Build Tools goals theo version đã pin.

Sau build, chạy đúng executable vừa tạo và thực hiện test/HTTP request tương ứng. Nếu compile fail, giữ compiler log đầy đủ. Nếu build pass nhưng feature fail lúc runtime, lưu exception, binary hash và request fixture.

## 9. Khi metadata dependency đã đầy đủ

Nếu JAR/repository cung cấp metadata đúng cho thao tác thư viện thực hiện, thường không cần khai báo lại cùng hints trong ứng dụng.

Tránh sao chép metadata rộng vào app vì hai nơi có thể lệch khi nâng dependency, gây khó review và buộc application tự duy trì metadata không thuộc code của mình.

Giữ dependency version được pin, ghi nhận nguồn metadata và thêm native regression test để phát hiện nếu nâng version làm metadata thay đổi.

## 10. Khi dependency thiếu metadata: bổ sung RuntimeHints

Nếu xác định thư viện cần constructor reflection nhưng không có metadata phù hợp, ứng dụng có thể đăng ký hint:

```java
package com.example.api;

import com.vendor.docs.PdfFormatter;
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class DocumentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            PdfFormatter.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
        );
    }
}
```

Ví dụ chỉ đăng ký constructor. Nếu stack trace chứng minh thư viện cần method/field khác, đăng ký đúng member category tương ứng. API cụ thể phải khớp Spring Framework version của project.

Đăng ký registrar với Spring AOT:

```java
package com.example.api;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(DocumentRuntimeHints.class)
public class NativeRuntimeHintsConfiguration {
}
```

Nếu registrar thuộc thư viện dùng chung, có thể đóng gói trong thư viện theo cơ chế Spring hỗ trợ cho version tương ứng. Nếu chỉ phục vụ cách application gọi thư viện, giữ hints ở application module thường dễ quản lý hơn.

## 11. Kiểm thử registrar bằng RuntimeHintsPredicates

Viết test xác nhận hint đã đăng ký:

```java
class DocumentRuntimeHintsTest {

    @Test
    void registersPdfFormatterConstructor() {
        RuntimeHints hints = new RuntimeHints();

        new DocumentRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onType(PdfFormatter.class)
                .withMemberCategory(
                    MemberCategory.INVOKE_DECLARED_CONSTRUCTORS
                )
                .test(hints)
        ).isTrue();
    }
}
```

Import và test dependencies phụ thuộc Spring Framework version. Test này kiểm tra registrar, không thay thế native integration test.

## 12. Không trùng lặp metadata từ dependency và application

Trước khi thêm hint, lập bảng đối chiếu:

| Thao tác thư viện | Dependency metadata | Application hint | Quyết định |
|---|---|---|---|
| Gọi constructor PdfFormatter | Đã có | Chưa có | Dùng metadata dependency |
| Gọi method qua reflection | Thiếu | Đã đăng ký method cần thiết | Giữ hint ứng dụng |
| Đọc template theo pattern | Đã có pattern phù hợp | Chưa có | Không đăng ký trùng |
| Tạo JDK proxy | Chưa xác minh | Chưa có | Điều tra và test trước |

Bảng chỉ minh họa. Điền dữ liệu thực tế dựa trên stack trace, vendor docs, metadata files và native test.

Nếu metadata dependency đã có nhưng sai/thiếu cho version đang dùng, cân nhắc nâng version, báo vendor hoặc tạo hint bổ sung có test. Không xóa metadata upstream chỉ để thay bằng bản copy local.

## 13. Metadata khác dependency và application configuration

Metadata mô tả khả năng runtime cần cho thư viện, ví dụ reflection/resource/proxy. Nó không thay thế:

- Dependency JAR thực tế.
- Spring bean registration.
- Profile hoặc conditional configuration.
- External configuration/secret.
- OS shared library.
- File runtime được mount.

Nếu PdfFormatter không có trong runtime classpath, reflection hint không tải class vào application. Nếu Spring bean bị AOT condition loại, hint không tạo bean. Nếu thư viện cần font trên filesystem, resource metadata không tự cài font vào container.

Chẩn đoán đúng lớp nguyên nhân trước khi thêm metadata.

## 14. Dùng tracing agent như nguồn bằng chứng bổ sung

Nếu vendor không có metadata và chưa rõ member nào được gọi động, tracing agent có thể quan sát test scenarios chạy trên JVM.

1. Chạy ứng dụng với tracing agent theo GraalVM version.
2. Thực thi các feature scenario đại diện.
3. Thu output reflection/resource/proxy/JNI.
4. Review từng entry và loại phần không cần.
5. Chuyển metadata vào RuntimeHints hoặc metadata format phù hợp.
6. Build Native Image và chạy lại test trên native.

Agent chỉ ghi những gì đã xảy ra trong scenarios quan sát. Nó không bảo đảm phát hiện subtype hiếm, error path hoặc plugin chưa được kích hoạt.

## 15. Nâng dependency và quản lý metadata theo version

Metadata gắn với hành vi cụ thể của dependency version. Khi nâng thư viện:

- Kiểm tra release notes và Native Image support statement.
- So sánh metadata trong JAR hoặc repository.
- Kiểm tra metadata có đổi type/member/resource pattern không.
- Chạy JVM và native integration tests.
- Loại hints ứng dụng đã trở nên dư thừa nếu có bằng chứng.
- Giữ lockfile và dependency version rõ ràng.

Không xóa application hint chỉ vì version mới có metadata; xác minh metadata mới bao phủ đúng thao tác và được nạp trong build thực tế.

## 16. Quy trình thực hành từ đầu đến cuối

1. Chọn dependency có thao tác động và tài liệu Native Image.
2. Thêm dependency vào runtime classpath của application module.
3. Ghi version và dependency graph.
4. Kiểm tra JAR dưới META-INF/native-image/ và metadata repository.
5. Đọc metadata để xác định type/member/resource được hỗ trợ.
6. Viết JVM integration test cho feature thật.
7. Build native và chạy test để xác minh.
8. Nếu thiếu metadata, xác định thao tác động từ stack trace/agent.
9. Thêm RuntimeHints hẹp tại application hoặc nâng dependency nếu upstream đã sửa.
10. Test registrar bằng RuntimeHintsPredicates.
11. Chạy Spring AOT, Native Image compile và native integration test.
12. Đóng gói final container và test feature trong image phát hành.
13. Lưu dependency version, metadata source, test result và binary/image digest.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Dependency có metadata nhưng native vẫn fail | Metadata không bao phủ member/feature đang dùng | Đọc metadata và stack trace |
| Metadata repository không được tải | Plugin/version/config chưa bật repository | Kiểm tra Native Build Tools docs và build log |
| Hint không có tác dụng | Registrar không được import/phát hiện | Kiểm tra AOT configuration/generated output |
| Class không tìm thấy | Dependency không có trong runtime classpath | Kiểm tra dependency graph |
| Bean không tồn tại | Spring AOT condition/profile loại bean | Kiểm tra bean graph, không thêm reflection hint |
| Resource thiếu | Pattern/resource metadata chưa đủ hoặc file không có | Kiểm tra JAR và runtime filesystem |
| JVM test pass, native fail | Test chưa chạy native hoặc metadata thiếu | Thêm native regression test |
| Hint quá rộng | Đăng ký toàn bộ member/package | Thu hẹp theo thao tác đã quan sát |
| Nâng dependency làm lỗi quay lại | Metadata thay đổi giữa version | Diff metadata và chạy lại feature tests |

## 18. Checklist hoàn thành

- Dependency thật được thêm vào đúng application runtime classpath.
- Version và transitive dependency graph được ghi lại.
- Đã kiểm tra metadata trong JAR và/hoặc reachability metadata repository.
- Đã xác minh metadata được Native Build Tools nạp trong build.
- Có JVM integration test cho API thực tế của dependency.
- Có native test tái hiện và xác nhận feature.
- Không thêm hints trùng nếu dependency metadata đã đủ.
- Nếu thiếu metadata, registrar chỉ đăng ký type/member/resource cần thiết.
- Registrar được Spring AOT phát hiện.
- RuntimeHintsPredicates test pass.
- Native executable và final container image đều được kiểm thử.
- Có regression test cho feature và version dependency.
- Lưu nguồn metadata, dependency version, log và artifact digest.

## 19. Câu hỏi tự kiểm tra

1. Reachability metadata repository khác metadata được đóng gói trong JAR như thế nào?
2. Làm thế nào xác minh dependency version thực tế trong application runtime classpath?
3. Vì sao phải kiểm tra metadata trước khi viết RuntimeHints?
4. Khi nào nên dùng metadata upstream và khi nào cần application registrar?
5. RuntimeHints có thể sửa dependency hoặc Spring bean bị thiếu không?
6. RuntimeHintsPredicates chứng minh được điều gì?
7. Vì sao tracing agent không bao phủ mọi thao tác động?
8. Khi nâng dependency, cần kiểm tra lại metadata và native tests ra sao?

**Ghi nhớ:** kiểm tra metadata upstream trước, xác định chính xác thao tác động còn thiếu rồi bổ sung RuntimeHints tối thiểu ở đúng nơi sở hữu. Xác minh registrar, chạy native integration test và kiểm thử final container để chứng minh dependency hoạt động trên artifact sẽ phát hành.
