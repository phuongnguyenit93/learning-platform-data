# Tự động hóa thay đổi cơ học và kiểm tra diff của mã sinh

Trong **Java Advance Compatibility Migration**, nhiều thay đổi phải được thực hiện đồng loạt ở hàng chục module: đổi import, thay annotation, cập nhật API, chỉnh Gradle/Maven, tái sinh REST client từ OpenAPI, tái sinh Protobuf classes hoặc cập nhật mapper được tạo bởi annotation processor. Nếu chỉnh sửa thủ công, nhóm dễ bỏ sót, tạo code không nhất quán và mất nhiều thời gian giải quyết những diff khổng lồ.

Tự động hóa giúp giảm công việc lặp lại, nhưng **một thay đổi được tạo tự động không mặc nhiên đúng**. Thay package có thể làm compiler hết lỗi mà ứng dụng lại không nhận diện JPA entity; thay generator có thể sửa import Jakarta nhưng đồng thời đổi serialization defaults; công cụ rewrite có thể tạo thay đổi ngoài phạm vi hoặc làm một recipe tiếp tục sửa code mỗi lần chạy.

Bài học thuộc chương **Chiến lược chuyển đổi** này giải thích cách thiết kế **các phép sửa cơ học có kiểm soát**, lựa chọn công cụ AST-aware/recipe-based, quản lý **mã sinh (generated code)** như output của một quá trình có đầu vào rõ ràng, so sánh diff theo hợp đồng API/dữ liệu, và thiết kế CI gates có thể tái lập. Mục tiêu là một đợt migration mà người review hiểu rõ **điều gì thay đổi, tại sao thay đổi, đã kiểm chứng bằng cách nào và có thể rollback ra sao**.

## 1. Mechanical change và semantic change khác nhau ở đâu?

**Thay đổi cơ học (mechanical change)** là phép chuyển đổi theo một quy tắc có thể mô tả, áp dụng lặp lại với phạm vi rõ ràng.

Ví dụ:

- Đổi tên type/import sau khi đã xác định API kế nhiệm.
- Di chuyển package và cập nhật references bằng IDE.
- Thay annotation type đã biết ở những module có dependency tương ứng.
- Chuyển một property key theo migration guide đã xác nhận.
- Cập nhật build configuration từ Java 11 sang Java 17 theo policy đã chọn.
- Chuyển các lời gọi API có mapping chính xác.
- Regenerate client/model khi input schema hoặc template được cập nhật.

**Thay đổi ngữ nghĩa (semantic change)** tác động hành vi hoặc hợp đồng mà client, database, runtime hay business logic phụ thuộc.

Ví dụ:

- Đổi cách xác thực và ủy quyền request.
- Thay serializer và cách biểu diễn null, date/time hoặc unknown fields.
- Đổi database transaction boundaries.
- Thay retry behavior của HTTP client.
- Đổi field number của Protobuf.
- Chuyển một API đồng bộ sang bất đồng bộ.

Một migration thường có **cả hai phần**: công cụ có thể sửa source theo mẫu, còn con người cùng tests xác minh ý nghĩa.

### 1.1. Ví dụ một sửa đổi nhìn đơn giản

Trước:

~~~java
import javax.persistence.Entity;
~~~

Sau:

~~~java
import jakarta.persistence.Entity;
~~~

Đây là bước cơ học phù hợp **nếu** module đã chuyển sang Jakarta Persistence. Tuy nhiên, không đủ để bảo đảm Hibernate 6 nhận diện entity, repository queries hoạt động hoặc schema không đổi.

### 1.2. Phân loại trước khi dùng công cụ

| Loại thay đổi | Ví dụ | Chiến lược |
|---|---|---|
| Cơ học rõ ràng | Rename chính xác type đã xác định | AST-aware recipe |
| Cơ học có điều kiện | `javax.persistence` → `jakarta.persistence` | Recipe theo module và dependency |
| Cấu hình build | Java release, plugin version, BOM | Script/structured config edit, review |
| Ngữ nghĩa | Security matcher, retry, serialization | Thiết kế + contract tests |
| Mã sinh | DTO, mapper, stubs, DB models | Sửa input/generator rồi regenerate |
| Binary generated | Compiler AST/bytecode transformation | Bytecode/API inspection và runtime tests |

Không nên gom các loại trên vào một thao tác tìm-thay văn bản duy nhất.

## 2. Vì sao tự động hóa đặc biệt quan trọng khi nâng Java?

Java migrations thường có những thay đổi diện rộng:

1. Chuyển từ JDK 8/11 lên 17 hoặc 21.
2. Thay các API bị loại khỏi JDK hoặc bị đóng gói chặt hơn.
3. Nâng Spring Boot/Spring Framework và chuyển các Jakarta EE APIs.
4. Cập nhật thư viện reflection, bytecode, testing và instrumentation.
5. Cập nhật Gradle/Maven compiler, plugin và dependency versions.
6. Tái sinh source từ OpenAPI, protobuf, Avro hoặc database schema.
7. Chỉnh configuration files phù hợp framework target.
8. Thay mã nguồn đang sử dụng API deprecated.
9. Cập nhật CI/CD và container image.
10. Xác minh Java source/bytecode mới trên runtime đích.

Các thay đổi này có thể lặp lại trên nhiều service. Một **recipe được kiểm chứng** giúp giảm chênh lệch do các nhóm tự sửa theo những cách khác nhau.

Tuy nhiên, tự động hóa chỉ có lợi khi biết rõ **tổ hợp phiên bản** mà ứng dụng hướng đến. Một recipe Jakarta áp lên module vẫn dùng Spring Framework 5 có thể tạo thêm lỗi thay vì giải quyết vấn đề.

## 3. Nguyên tắc vàng: source of truth và quyền sở hữu

Trước khi sửa một file, cần biết **file đó được viết tay hay được sinh**.

~~~text
Handwritten Java source
    |
    +--> IDE / OpenRewrite / manual review
    |
    v
Updated application source

Schema / template / annotations / DB metadata
    |
    +--> Generator / annotation processor
    |
    v
Generated Java / resources / bytecode
~~~

Quy tắc:

- **Source viết tay:** có thể refactor trực tiếp bằng công cụ thích hợp.
- **Generated source:** ưu tiên sửa **schema, template, generator config/version**, rồi chạy lại generator.
- **Generated bytecode/AST:** kiểm tra compiler/processor, không kỳ vọng luôn có file Java để diff.
- **Build outputs:** tránh chỉnh tay vì thường sẽ bị ghi đè.

Nếu không biết owner của file, cần điều tra trước khi áp dụng rewrite.

### 3.1. Dấu hiệu nhận diện generated files

Có thể thấy:

- Header `Generated by...`.
- Annotation `@Generated`.
- Directory như `build/generated` hoặc `target/generated-sources`.
- Package `client.generated` theo naming convention.
- Task code generation trong Gradle/Maven.
- Schema hoặc template được ghi trong comment.
- File được thay mỗi khi build chạy.

Không dùng dấu hiệu duy nhất để kết luận: một số generator không gắn annotation, hoặc nhóm từng copy generated source vào một package thông thường.

## 4. Hai chính sách lưu generated code

### 4.1. Commit generated output vào Git

Ví dụ:

~~~text
api/orders.yaml               <- source of truth
src/generated/java/           <- generated files được commit
build.gradle                  <- generator configuration
~~~

Ưu điểm là pull request có thể review trực tiếp diff của DTO/client; người dùng repository không nhất thiết phải chạy generator mỗi lần mở project.

Nhược điểm là repository lớn, dễ có output stale hoặc bị sửa tay. CI nên tái sinh output rồi **so với phiên bản đã commit**.

### 4.2. Chỉ lưu generated output trong build directory

Ví dụ:

~~~text
src/main/openapi/orders.yaml  <- source of truth
build/generated/openapi/      <- ignored build output
~~~

Ưu điểm là giảm diff và tránh lưu implementation do máy tạo. Nhược điểm là Git diff thông thường **không thấy** output, và CI phải có khả năng tái sinh chính xác.

Trường hợp này cần snapshot comparison, generated API report, schema compatibility checks hoặc build artifacts để reviewer thấy thay đổi. Không thể lấy `git diff` rỗng làm bằng chứng codegen đúng nếu outputs bị ignore.

### 4.3. Chính sách phải rõ trong từng module

Nếu một service commit generated DTOs còn service khác chỉ tạo trong build, cả hai đều có thể hợp lý. Nhưng phải ghi:

- Nơi đặt input gốc.
- Tool và version tạo output.
- Đường dẫn output.
- Có được commit output hay không.
- Người chịu trách nhiệm review.
- Lệnh/tác vụ dùng để regenerate.
- Tiêu chí CI khi output stale.

## 5. Baseline trước khi tự động hóa

Một phép rewrite chỉ có ý nghĩa nếu biết trạng thái ban đầu.

Nên lưu:

| Hạng mục | Nội dung |
|---|---|
| Git baseline | Commit/tag, working tree status |
| Java toolchain | Vendor/version, `--release` |
| Build tool | Gradle/Maven wrapper và plugins |
| Dependency graph | Direct/transitive versions, BOM |
| Generator | Tool, plugin, template và versions |
| Input | OpenAPI/proto/schema/annotations cùng checksums |
| Output | Generated files hoặc artifact trước migration |
| Behavior | Test counts, contract fixtures, integration baselines |
| Runtime | Container image, locale, timezone nếu ảnh hưởng |
| Ownership | Ai phê duyệt thay đổi API/data/security |

Ví dụ lệnh khảo sát repository cho người thực hiện:

~~~bash
git status --short
git rev-parse HEAD
git diff --stat
~~~

Một working tree có sẵn thay đổi chưa được ghi nhận sẽ khiến diff của công cụ trộn với diff của người khác. Hãy tạo branch/commit baseline rõ trước khi chạy batch rewrite.

## 6. Chọn công cụ đúng với loại thay đổi

| Công cụ | Điểm mạnh | Giới hạn |
|---|---|---|
| IDE Rename/Move refactoring | Hiểu symbol và imports trong project | Cần project model đúng |
| OpenRewrite | Recipes có cấu trúc, chạy nhiều module | Phụ thuộc recipe/tool compatibility |
| JavaParser/JDT | Tự viết AST transformation | Phải quản lý type resolution |
| Error Prone/Refaster | Một số pattern compiler-aware | Gắn với javac/plugin version |
| Structured XML/YAML edits | Cấu hình có schema rõ | Có thể thay formatting/ordering |
| Regex/text replacement | Chuỗi bất biến, phạm vi nhỏ | Không hiểu type/behavior |
| OpenAPI/protoc/jOOQ generators | Tạo source từ schema | Output thay theo toolchain |
| Manual review | Phân tích hợp đồng và security | Cần thời gian nhưng không thể loại bỏ |

Không phải mọi dự án đều cần OpenRewrite. Một rename trong một module nhỏ có thể làm bằng IDE an toàn hơn xây cả framework recipe. Ngược lại, một phép chuyển hàng nghìn call sites trên nhiều repositories có thể đáng để đầu tư recipe và tests cho recipe.

## 7. Vì sao regex có thể phá migration Javax/Jakarta?

Ví dụ một quy tắc text:

~~~text
Thay mọi "javax." thành "jakarta."
~~~

Nó sẽ ảnh hưởng cả các Java SE imports vẫn hợp lệ:

~~~java
import javax.net.ssl.SSLContext;
import javax.crypto.Cipher;
import javax.sql.DataSource;
import javax.naming.InitialContext;
import javax.management.MBeanServer;
~~~

Các imports đó không có mapping tổng quát sang `jakarta.*`.

Tương tự, tìm-thay có thể sửa:

- String literals dùng reflection.
- XML metadata.
- Comments hoặc documentation.
- Generated test fixtures.
- Code thuộc module vẫn chạy framework cũ.
- Package names có từ tương tự nhưng type không giống nhau.

**Không dùng phép thay theo prefix làm quyết định API migration.** Nên thay từng nhóm API, với preconditions rõ.

### 7.1. Tìm bằng ripgrep để khảo sát

~~~bash
rg -n 'javax\.(servlet|persistence|validation)\.' src
rg -n 'WebSecurityConfigurerAdapter|antMatchers' src
rg -n 'sun\.|jdk\.internal\.' src/main/java
~~~

Kết quả là **ứng viên cần phân loại**, không phải lệnh yêu cầu thay tất cả dòng được tìm thấy.

## 8. AST-aware refactoring là gì?

AST (Abstract Syntax Tree) biểu diễn cấu trúc chương trình: import declaration, type reference, annotation, method invocation, lambda, class declaration và nhiều thành phần khác.

Một AST-aware tool có thể phân biệt:

~~~java
import javax.persistence.Entity;

@Entity
public class OrderEntity {
}
~~~

với:

~~~java
String doc = "javax.persistence.Entity";
~~~

Bằng type attribution, một recipe có thể tập trung vào type reference đúng thay vì thay mọi đoạn text có cùng chuỗi ký tự.

### 8.1. Giới hạn của AST

AST không tự chứng minh:

- HTTP endpoint còn authorization đúng.
- Database schema không bị thay.
- Protobuf wire format còn tương thích.
- Serializer xử lý null/date/time giống nhau.
- Runtime có đúng implementation của interface mới.

Vì vậy, **đổi cấu trúc source thành công** và **migration behavior thành công** là hai kết quả khác nhau.

## 9. OpenRewrite recipe: ví dụ hẹp

OpenRewrite hỗ trợ recipes chuyển đổi Java/build/config source. Ví dụ một declarative recipe đổi annotation type:

~~~yaml
type: specs.openrewrite.org/v1beta/recipe
name: com.example.migration.UseJakartaEntity
displayName: Use Jakarta Persistence Entity annotation
description: Replace the known Java EE Entity type.
recipeList:
  - org.openrewrite.java.ChangeType:
      oldFullyQualifiedType: javax.persistence.Entity
      newFullyQualifiedType: jakarta.persistence.Entity
~~~

Recipe trên **chỉ chuyển một type reference**. Nó không thay toàn bộ JPA, không nâng Hibernate 6 và không bảo đảm ORM nhận diện entity.

Với dự án đã cấu hình OpenRewrite Gradle plugin, có thể có:

~~~bash
./gradlew rewriteDryRun
./gradlew rewriteRun
~~~

Với Maven plugin đã cài:

~~~bash
mvn rewrite:dryRun
mvn rewrite:run
~~~

Các tasks/goals phụ thuộc plugin/version và cấu hình dự án. Không mặc định chúng tồn tại trong mọi repository.

### 9.1. Dry run trước rồi mới apply

Quy trình:

1. Chọn đúng plugin và recipe version.
2. Chạy dry run và xem danh sách files.
3. Xác nhận không sửa ngoài phạm vi.
4. Apply recipe trên branch migration.
5. Xem source diff và dependency graph.
6. Chạy compile/test theo quy trình dự án.
7. Chạy recipe lần hai để kiểm tra idempotency.
8. Commit source cùng tài liệu recipe/version.

### 9.2. Pin recipe version

Một recipe name có thể giữ nguyên nhưng implementation được cập nhật ở bản mới. Khi mục tiêu là tái lập migration, ghi:

- Build tool wrapper.
- OpenRewrite plugin version.
- Recipe artifact version.
- Active recipe names/order.
- JDK dùng chạy tool.
- Đường dẫn/mô-đun được xử lý.

Không dùng một nhãn chung “latest recipe” làm bằng chứng review.

## 10. Thiết kế recipes nhỏ và có điều kiện

Một recipe lớn thay Java baseline, Spring Security, Hibernate, generated OpenAPI client và logging trong cùng lượt tạo diff rất khó hiểu.

Có thể chia:

~~~text
R1: Java imports/types thuộc Jakarta Persistence
R2: Jakarta Bean Validation trong module đã nâng stack
R3: API method rename theo migration guide
R4: Build configuration/JDK toolchain
R5: Cleanup các deprecated constructs an toàn
Manual: Security, transactions, schema và protocol
Generated: Regenerate từ schema/config mới
~~~

Điều kiện cho R1 có thể là “module đã dùng Jakarta Persistence API được quản lý bởi framework mục tiêu”, không phải “mọi module trong repo”.

### 10.1. Idempotency

Recipe `R` áp dụng lên source `S` nên có tính chất mong đợi:

\[
R(R(S)) = R(S)
\]

Chạy lại một recipe không nên tiếp tục thêm annotation, đổi format qua lại hoặc lặp đoạn code. Nếu lần thứ hai vẫn tạo diff mới, cần xem điều kiện match hoặc độ ổn định output.

**Idempotency chưa chứng minh kết quả đúng.** Một chuyển đổi sai nhưng ổn định vẫn cho kết quả idempotent; cần tests và review.

### 10.2. Thứ tự recipes

Có lúc recipe B chỉ match sau khi recipe A đổi type. Khi đó A → B và B → A có thể không tương đương. Ghi sequence rõ trong build hoặc migration runbook.

## 11. Ví dụ chuyển JPA entity cơ học

Trước:

~~~java
package com.example.orders;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;
}
~~~

Sau:

~~~java
package com.example.orders;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class OrderEntity {

    @Id
    private Long id;
}
~~~

Diff có thể được tạo tự động, nhưng để kết luận hoàn tất vẫn phải xác minh:

- Jakarta Persistence API đã có trong dependency graph.
- Hibernate/framework version phù hợp.
- Entity scanning hoạt động.
- Custom converters, listeners và query APIs được chuyển.
- SQL, sequence và schema behavior phù hợp.
- Integration tests trên database đại diện được chạy.

Đây là ví dụ **cơ học hóa điều xác định được** mà vẫn giữ review đối với phần ngữ nghĩa.

## 12. Các thay đổi cần người quyết định semantics

### 12.1. Spring Security 5 sang 6

Chuyển từ `WebSecurityConfigurerAdapter` sang `SecurityFilterChain` không chỉ đổi syntax. Cần xác minh request matchers, authorization order, CSRF, session, CORS, method security và OAuth/JWT validation.

Không tự thêm `permitAll()` hoặc vô hiệu hóa CSRF để build/test pass.

### 12.2. Date/time

Đổi `SimpleDateFormat` sang `DateTimeFormatter` có thể thay parsing strictness, locale, timezone và error behavior. Phải có golden inputs, kể cả timestamp biên và daylight-saving cases khi có liên quan.

### 12.3. HTTP client

Thay thư viện HTTP có thể đổi timeout defaults, redirect policy, connection pooling, TLS verification và retry. Dù API signatures sửa được theo recipe, integration/network behavior phải test riêng.

### 12.4. Serialization

Đổi thư viện JSON/XML hoặc generated DTO có thể đổi field names, optional/null handling, enum values và protocol compatibility. Đây là nơi **diff rất nhỏ có thể gây breaking change lớn**.

## 13. Generated code như kết quả của một hàm

Có thể mô hình hóa quá trình sinh:

\[
G(I,T,C,E)=O
\]

Trong đó:

- `I`: input schema/source/annotations/DB metadata.
- `T`: generator implementation và version.
- `C`: config, options, custom templates.
- `E`: môi trường JDK, OS, locale, timezone, filesystem.
- `O`: output mã sinh.

Để diff có ý nghĩa, phải biết **đã thay đổi biến nào**.

Nếu vừa đổi OpenAPI schema, nâng generator, đổi JDK và formatter, output diff có thể rất lớn. Khi đó khó phân biệt business contract change và template/tool change.

### 13.1. Thay một biến tại một thời điểm khi có thể

Ví dụ:

~~~text
Baseline:
  orders.yaml checksum A
  generator version X
  JDK 17
  templates checksum T

Candidate:
  orders.yaml checksum B
  generator version X
  JDK 17
  templates checksum T
~~~

Diff chủ yếu nên phản ánh thay đổi schema. Nếu muốn nâng generator X → Y, nên cân nhắc tạo PR/commit riêng để hiểu tool-only diff.

## 14. Nguồn sinh mã phổ biến trong Java

| Công nghệ | Đầu vào | Output | Rủi ro diff |
|---|---|---|---|
| OpenAPI Generator | OpenAPI YAML/JSON | API clients, DTOs, server interfaces | HTTP contract, annotations, nullability |
| protoc/gRPC | `.proto` | Message classes, stubs | Field numbers, wire format, methods |
| Avro compiler | Avro schema | Records/serializers | Schema evolution, defaults |
| jOOQ | Database schema | Table/record/DAO classes | SQL type, naming, metadata |
| MapStruct | Mapper interfaces | Mapper implementations | Null handling, nested mappings |
| JPA metamodel processors | Entity annotations | Static metamodel types | Javax/Jakarta versions |
| QueryDSL processors | Domain/JPA model | Query types | Processor classifier/API |
| JAXB/XJC | XSD | Java XML models | XML schema, javax/jakarta binding |
| Lombok | Annotations/AST | Transformed compiler output | Compiler internals, bytecode behavior |

Cần biết **công cụ nào sinh file nào**. Không giả định tất cả đều tạo `.java` trong cùng một directory.

## 15. Generated marker và vấn đề javax.annotation

Khi nâng JDK/Jakarta, các generator có thể sinh:

~~~java
import javax.annotation.Generated;
~~~

Trong Java hiện đại, cần phân biệt:

- `javax.annotation.Generated` của một số hệ Java EE/legacy.
- `javax.annotation.processing.Generated` thuộc Java SE annotation processing API.
- `jakarta.annotation.Generated` thuộc Jakarta Annotations API.

Không áp regex thay tất cả thành một tên mới. Lựa chọn phụ thuộc generator/runtime/framework và việc annotation đó có được library tiêu thụ thực sự hay chỉ dùng làm metadata.

### 15.1. Khi generated code compile lỗi

~~~text
error: package javax.annotation does not exist
~~~

Cách điều tra:

1. Xác định generator/plugin tạo import.
2. Xem generator release và Java/Jakarta target.
3. Cập nhật option/template hoặc version có hỗ trợ.
4. Regenerate toàn bộ output.
5. Kiểm tra diff và compile.
6. Không sửa tay hàng trăm generated files nếu generator vẫn sinh import cũ.

Một generator có thể **chạy được trên JDK 17 nhưng vẫn sinh source chỉ phù hợp framework cũ**. Hai điều kiện tương thích này khác nhau.

## 16. Input và output của một generator phải được kiểm soát

Ví dụ OpenAPI:

~~~text
src/main/openapi/orders.yaml
        |
        | Generator version + config + templates
        v
build/generated/openapi/
        +-- api/OrdersApi.java
        +-- model/OrderDto.java
        +-- ApiClient.java
~~~

Nếu cần đổi DTO field, kiểm tra OpenAPI schema và contract, không chỉ sửa `OrderDto.java`.

Ví dụ Protobuf:

~~~text
src/main/proto/orders.proto
        |
        | protoc + Java/gRPC plugins
        v
build/generated/source/proto/main/
        +-- java/...message classes
        +-- grpc/...service stubs
~~~

Nếu muốn đổi field, cần hiểu field numbers, unknown fields và backward compatibility trước khi regenerate.

## 17. Generator determinism và build reproducibility

Một generator **deterministic** khi cùng input, toolchain, configuration và môi trường phù hợp tạo ra cùng output.

Những nguyên nhân làm output thay không có chủ đích:

- Timestamp trong comments.
- Dynamic generator/dependency version.
- Thay JDK hoặc annotation processor implementation.
- Locale/timezone khác.
- Không ổn định thứ tự iteration của collections.
- Filesystem traversal order khác.
- Line endings CRLF/LF khác.
- Encoding không cố định.
- Custom templates chưa pin checksum.
- Incremental build dùng stale cache.
- Nhiều tasks ghi vào cùng output directory.

### 17.1. Ví dụ nhiễu timestamp

~~~diff
-// Generated at 2026-11-10 09:15:00
+// Generated at 2026-11-12 13:05:00
~~~

Nên **tắt timestamp output** bằng option của generator nếu có, thay vì sử dụng một bộ lọc diff rộng có thể che mất thay đổi hợp đồng thật.

### 17.2. Chuẩn hóa môi trường

Một migration yêu cầu reproducibility có thể pin:

- JDK toolchain.
- Locale và timezone nếu ảnh hưởng sinh code.
- File encoding UTF-8.
- Build tool wrapper.
- Plugin/generator versions.
- Template versions.
- Schema checksum.
- Formatter/line ending policy.

`.gitattributes` có thể hỗ trợ thống nhất line endings cho mã sinh được commit. Tuy nhiên, đổi line-ending policy và đổi schema trong cùng PR có thể làm mọi file bị đánh dấu modified; nên phân chia nếu có thể.

## 18. Quy trình so sánh baseline và candidate generated output

~~~text
Baseline commit
    |
    +--> Generator phiên bản đã pin
    |
    v
Output A
    |
    | Thay đổi schema/template/tool có chủ đích
    v
Candidate commit/config
    |
    +--> Generator tương ứng đã pin
    |
    v
Output B
    |
    v
Diff A vs B
    |
    +--> Expected API changes
    +--> Template/tool-only changes
    +--> Formatting/noise
    +--> Unexpected/deleted files
    |
    v
Review + contract/integration tests
~~~

Nếu không tái sinh được baseline output từ baseline input, hãy xử lý reproducibility trước. Nếu không, diff A vs B sẽ trộn cả lỗi generator environment với mục tiêu migration.

## 19. Đọc Git diff theo từng tầng

Các lệnh tham khảo:

~~~bash
git status --short
git diff --stat
git diff --name-status
git diff HEAD -- src/main/java
git diff HEAD -- src/generated/java
~~~

`--stat` và `--name-status` giúp nhận biết file được thêm, sửa, xóa hoặc có thay đổi bất thường ngoài scope. Với các PR có nhiều commits, cần chọn rõ baseline branch/commit và phạm vi so sánh phù hợp.

### 19.1. Kiểm tra whitespace

~~~bash
git diff --check HEAD -- src/main/java src/generated/java
~~~

Lệnh này phát hiện một số whitespace errors trong diff. Nó không xác minh Java code hoặc API contracts.

### 19.2. Word diff

~~~bash
git diff --word-diff HEAD -- src/generated/java
~~~

Hữu ích khi một import/type đổi vài tokens. Nhưng đừng bỏ normal diff: cấu trúc class, annotations và dòng bị xóa có thể dễ bị đọc sai trong word diff.

### 19.3. Ignore whitespace chỉ để chẩn đoán

~~~bash
git diff --ignore-space-change HEAD -- src/generated/java
~~~

Lệnh giúp biết nhiễu whitespace lớn hay nhỏ; **không dùng làm quality gate duy nhất**, vì một số thay đổi source vẫn cần được review dù hình thức có vẻ ít khác.

## 20. Tracked, untracked và ignored files

`git diff --exit-code HEAD -- path` kiểm tra tracked files khác commit HEAD nhưng **không tự báo file untracked mới**.

Với generated output được commit, dùng thêm:

~~~bash
git ls-files --others --exclude-standard -- src/generated/java
~~~

Lệnh liệt kê những file untracked không bị Git ignore trong phạm vi.

### 20.1. Ví dụ CI freshness gate

Ví dụ shell kiểu Unix trên **clean checkout**:

~~~bash
set -eu

# Task chỉ minh họa; thay bằng task generator của dự án.
./gradlew generateClientSources

# Tracked output không được thay nếu đã commit đúng.
git diff --check HEAD -- src/generated/java
git diff --exit-code HEAD -- src/generated/java

# Không có output mới chưa được track.
if [ -n "$(git ls-files --others --exclude-standard -- src/generated/java)" ]; then
    echo "Generated files chưa được commit"
    exit 1
fi
~~~

Điểm quan trọng:

- Task `generateClientSources` phải thật sự tồn tại/được cấu hình.
- CI phải bắt đầu từ một checkout biết trạng thái.
- `git diff HEAD` phát hiện tracked changes, kể cả thay đổi đã staged trong những hoàn cảnh tương ứng.
- Untracked check là bước riêng.
- Nếu generated directory bị ignore thì hai checks Git này **không đủ**; cần chiến lược snapshot/artifact.
- Gate chứng minh source được commit khớp với generator, **không chứng minh API mới tương thích**.

## 21. Diff cho generated output chỉ có trong build/

Nếu mã sinh không commit, hãy lưu snapshots hoặc artifacts từ các lần generate.

Ví dụ dành cho môi trường có shell Unix và `diff`:

~~~bash
./gradlew clean generateClientSources
cp -R build/generated/client /tmp/generated-run-a

# Cùng input và cùng toolchain.
./gradlew --rerun-tasks generateClientSources

diff -ru /tmp/generated-run-a build/generated/client
~~~

Ý nghĩa:

- Hai lần với cùng inputs giúp kiểm tra **determinism**.
- Muốn xem candidate khác baseline, phải tạo hai snapshots từ **hai inputs/configurations** xác định.
- `diff -ru` trả exit code khác 0 khi có khác biệt; cần xử lý trong CI tùy mục tiêu.
- Trên Windows PowerShell có thể dùng cơ chế so sánh tương đương; cú pháp `cp`/`diff` trên không mặc định tương đương.
- Nếu generator không xóa stale output, cần quản lý output clean để tránh file cũ lọt vào snapshot.

### 21.1. Determinism không đồng nghĩa correctness

Generator có thể luôn sinh cùng một source sai; lúc đó deterministic nhưng không đúng nghiệp vụ. Ngược lại, source mới có thay đổi đúng vì schema thay đổi có chủ đích. Cần **cả reproducibility check và contract tests**.

## 22. Phân loại diff mã sinh theo rủi ro

| Nhóm diff | Ví dụ | Quyết định |
|---|---|---|
| Import Jakarta | `javax.validation` → `jakarta.validation` | Kiểm tra target stack |
| Public API | Thêm/xóa method, đổi parameter/return type | API/ABI review |
| Data model | Nullable → required, enum đổi, field mất | Contract/schema review |
| Wire format | Protobuf number, XML/JSON field name | Cross-version tests |
| Runtime dependency | Serializer, HTTP client, annotation library | Behavior/security review |
| SQL model | Column/type/PK đổi | Database migration review |
| Generated comment | Timestamp, version header | Giảm noise |
| Formatting | CRLF/LF, indentation | Tách khỏi semantic changes |
| File deletion/rename | Class/endpoint biến mất | Owner approval |
| Security-related metadata | Validation/auth annotation đổi | Security review |

Một diff sửa **một Protobuf field number** có thể nguy hiểm hơn 10.000 dòng đổi formatter. Không đánh giá rủi ro chỉ theo số dòng.

## 23. OpenAPI: diff do generator và schema

Giả sử có:

~~~text
api/orders.yaml
      |
      v
OpenAPI Generator
      |
      +-- OrdersApi.java
      +-- OrderDto.java
      +-- ApiClient.java
~~~

Khi nâng Spring Boot 2 → 3, generator có thể phải chuyển từ Javax sang Jakarta annotations.

Một diff hợp lý:

~~~diff
-import javax.validation.Valid;
-import javax.validation.constraints.NotNull;
+import jakarta.validation.Valid;
+import jakarta.validation.constraints.NotNull;
~~~

Nhưng nếu generator đồng thời đổi:

~~~diff
-public Long getOrderId()
+public String getOrderId()
~~~

thì phải điều tra schema, template hoặc type mapping. Đây có thể là **breaking API change**, không phải noise của Jakarta migration.

### 23.1. Nên tách đổi tool khỏi đổi schema

Có thể triển khai theo nhịp:

1. Pin generator và xác nhận baseline deterministic.
2. Đổi generator version/options, giữ schema không đổi.
3. Review tool-only/generated diff.
4. Sau đó đổi schema có chủ đích, regenerate.
5. Chạy API/serialization contracts.

Không bắt buộc mọi dự án đều tách thành đúng số PR này, nhưng cần giải thích rõ từng nguyên nhân trong diff.

## 24. Protobuf/gRPC: đừng xem field name là wire contract

Ví dụ:

~~~proto
syntax = "proto3";

package example.orders;

message Order {
  string id = 1;
  int64 created_at_epoch_ms = 2;
}
~~~

Thêm field:

~~~proto
message Order {
  string id = 1;
  int64 created_at_epoch_ms = 2;
  string note = 3;
}
~~~

có thể là một schema evolution tương thích theo điều kiện Protobuf, nhưng **đổi field number 2 thành 8** dù giữ tên field sẽ làm thay wire representation.

Các bước cần kiểm tra:

- Pin `protoc` và Java/gRPC plugin versions.
- Đối chiếu file `.proto` và generated Java source.
- Không tái sử dụng field numbers đã xóa tùy tiện.
- Quản lý reserved numbers/names nếu cần.
- Kiểm tra unknown fields và defaults.
- Test client cũ ↔ server mới, client mới ↔ server cũ.
- Xác minh service method names và gRPC status handling.

Một nâng protoc version có thể tạo diff lớn dù schema không đổi; đừng nhầm generator implementation diff với wire schema change.

## 25. Avro, JAXB và XML codegen

### 25.1. Avro

Generated Avro classes chịu ảnh hưởng schema fields, defaults, union types và logical types. Khi schema evolution, cần xem reader/writer schema compatibility, không chỉ compile generated Java.

### 25.2. JAXB và Java/Jakarta

Khi nâng JDK, JAXB không còn là bộ API mặc định đi kèm mọi JDK hiện đại. Project dùng XJC/XML Binding cần chọn generator và runtime implementation phù hợp.

Cần xác minh:

- Dùng `javax.xml.bind.*` hay `jakarta.xml.bind.*` theo target.
- Version của generator/XJC và runtime.
- XML namespaces, elements/attributes.
- Adapter/converter behavior.
- Marshal/unmarshal golden XML fixtures.

Không nên sửa tay hàng trăm imports trong generated JAXB classes rồi giữ generator cũ tạo lại chúng.

## 26. jOOQ và database-generated code

Ví dụ:

~~~text
Versioned DDL / database schema
       |
       v
jOOQ generator
       |
       +-- Tables
       +-- Records / POJOs
       +-- DAOs
~~~

Output có thể đổi vì:

- Database schema thực sự được migrate.
- JDBC driver/metadata resolution thay.
- jOOQ generator version đổi.
- Database dialect/version đổi.
- Naming strategy đổi.
- Catalog/schema filtering khác.
- Thứ tự metadata không ổn định.

### 26.1. Tạo schema cố định cho codegen

Tránh chạy code generation trên production database đang thay đổi ngoài kiểm soát. Ưu tiên dựng schema từ migration scripts hoặc schema snapshot có version, rồi tái sinh từ môi trường test xác định.

### 26.2. Review SQL/DB semantics

Một column type hoặc identifier generation strategy thay có thể làm generated class khác, nhưng còn phải kiểm tra persistence mappings, query plans, transaction behavior và rollback schema.

## 27. MapStruct, QueryDSL, JPA metamodel và processors

Annotation processors thường tạo output ở các đường dẫn như:

~~~text
build/generated/sources/annotationProcessor/java/main/
target/generated-sources/annotations/
~~~

Ví dụ MapStruct:

~~~java
@Mapper
public interface OrderMapper {
    OrderDto toDto(OrderEntity entity);
}
~~~

Implementation do processor tạo có thể khác khi đổi MapStruct version, compiler/JDK, Lombok integration hoặc null/default mapping options.

Các điểm review:

- Mapping khi input null.
- Nested objects và collections.
- Enum conversions.
- Field rename/defaults.
- Date/time conversion.
- Generated implementation có gọi setter/constructor khác không.
- Target framework component model và injection.

QueryDSL hoặc JPA metamodel processors có thể cần phiên bản tương thích **Jakarta Persistence** khi source entities chuyển từ `javax.persistence.*` sang `jakarta.persistence.*`. Sửa tay generated `QOrder.java` không giải quyết mismatch của processor.

### 27.1. Lombok không luôn tạo source file

Lombok có thể biến đổi compiler AST, không nhất thiết ghi implementation Java ở `build/generated`. Khi nâng JDK hoặc Lombok version, cần kiểm tra compiler integration, bytecode/API signatures, tests và delombok output nếu workflow có dùng.

## 28. Build cache và incremental generation

Một task generator có thể bị bỏ qua sai nếu build system không biết input đã thay.

Ví dụ nguyên nhân:

- Imported OpenAPI schema không nằm trong input file set.
- Custom template directory không được khai báo.
- Hai generators cùng ghi vào một folder.
- Task clean xóa output của task khác.
- Cache key không bao gồm Java/generator version.
- Annotation processor incremental behavior bị cấu hình sai.
- Output cũ còn lưu dù source entity đã xóa.
- Parallel build ghi đè file.

### 28.1. So clean và incremental output

Trong môi trường kiểm thử, có thể so:

~~~bash
./gradlew generateClientSources
./gradlew clean generateClientSources
~~~

Nếu outputs khác nhau trên cùng inputs, điều tra task dependencies và cache settings. **Không nên tắt mọi build cache vĩnh viễn** nếu lỗi gốc là task khai báo input/output chưa đủ.

### 28.2. Tách output directories

Mỗi generator nên có output riêng và build sẽ ghép source roots theo configuration. Tránh để hai generators ghi trực tiếp vào `src/main/java` hoặc cùng folder tracked trong Git mà không có cơ chế phối hợp.

## 29. Generated binary và mã không nhìn thấy dưới dạng .java

Một số biến đổi tạo bytecode hoặc AST thay vì source files:

- Lombok/compiler extensions.
- Bytecode weaving.
- Annotation-processing metadata.
- Class instrumentation.
- Runtime proxies.
- Resource descriptors.

Khi cần xem class-file version/API output:

~~~bash
javap -verbose -classpath build/classes/java/main \
  com.example.orders.OrderMapperImpl
~~~

Tuy nhiên, không nên yêu cầu compiled `.class` phải **byte-for-byte giống nhau** sau khi đổi JDK/compiler: debug information, constant pool ordering hoặc cách sinh bytecode có thể thay. Nếu binary khác, cần phân tích API và behavior, không chỉ nhìn hash.

## 30. Kiểm tra diff trong fat JAR và deployment artifact

Một repository có thể dùng đúng generated code trong `build/generated` nhưng artifact cuối lại chứa classes cũ do shading, packaging hoặc cache.

Những câu hỏi:

- Artifact có class mới không?
- Có hai bản generated class bị trùng không?
- Fat JAR/shaded JAR làm đổi package hoặc metadata không?
- WAR `WEB-INF/lib` chứa client/generator runtime đúng version không?
- Container cung cấp thư viện khác làm source build và runtime lệch nhau không?
- Class-file major của generated classes có chạy trên JDK đích không?
- Reflection metadata hoặc service registrations có còn được đóng gói không?

Lệnh tham khảo:

~~~bash
jar tf build/libs/orders-service.jar
jar tf target/orders-service.war
~~~

Đường dẫn phụ thuộc build system. **Diff source không thay thế kiểm tra artifact được deploy**.

## 31. Review diff theo ranh giới hợp đồng

Một reviewer không nhất thiết phải đọc từng method boilerplate trong 500 generated files; nhưng phải biết **những hợp đồng nào đã thay**.

Tập trung vào:

1. Public methods/classes/constructors.
2. HTTP paths, verbs, media types và status codes.
3. DTO fields, required/optional, nullability.
4. Bean Validation annotations.
5. JSON/XML property names và serialization.
6. Protobuf field numbers/enum values.
7. DB tables/columns/types/keys.
8. Authentication/authorization metadata.
9. Runtime dependencies, TLS/security defaults.
10. Files bị xóa/đổi package.

Một báo cáo hữu ích có thể ghi:

~~~text
Input diff:
  orders.yaml: thêm optional note field

Generator diff:
  version X -> version X (không đổi)

Generated diff:
  OrderDto.java: thêm field, accessor và annotation
  OrdersApi.java: không đổi method/path
  ApiClient.java: không đổi

Contract checks:
  old client -> new server: đã kiểm tra
  new client -> old server: đã kiểm tra
~~~

Đây chỉ là **mẫu cách trình bày**, không phải test results thực tế.

## 32. Pull request nên chia như thế nào?

Khi có thể, tách những nguyên nhân lớn:

- PR A: pin build/generator toolchain và bổ sung freshness gate.
- PR B: chạy mechanical recipe có scope rõ.
- PR C: nâng generator/Jakarta target với schema giữ nguyên.
- PR D: thay schema/API có chủ đích và kiểm tra backward compatibility.

Không bắt buộc dự án phải dùng chính xác bốn PR; mục tiêu là tránh một diff quá lớn mà không ai phân biệt được **tool-only** và **semantic** changes.

Mỗi PR nên ghi:

- Baseline commit.
- Tool/recipe/generator versions.
- Scope modules và paths.
- Expected diff categories.
- Unexpected changes đã được giải thích.
- Build/test/contract evidence.
- Owner/reviewer.
- Rollout và rollback nếu có ảnh hưởng runtime.

### 32.1. Code owners và approval

Một codegen diff có thể thuộc platform team về kỹ thuật, nhưng nếu nó thay API/protocol thì chủ sở hữu contract phải review. Một approval chỉ nhìn formatting không thay thế quyết định về compatibility.

## 33. Ma trận kiểm tra sau automation

| Hạng mục | Mechanical rewrite | Generated code |
|---|---|---|
| Scope và file diff | Bắt buộc | Bắt buộc |
| Tool/recipe version | Ghi nhận | Ghi nhận |
| Recipe idempotency | Khi dùng recipe | Không thay generator determinism |
| Generator determinism | Không áp dụng chung | Cần kiểm tra |
| Freshness so input | Nếu tác động codegen | Cần kiểm tra |
| Compile/type resolution | Cần | Cần |
| Public API/ABI diff | Khi có API change | Đặc biệt quan trọng |
| Schema/wire compatibility | Khi liên quan | Khi có protocol/model |
| Unit tests | Có | Có |
| Contract/integration tests | Theo mức rủi ro | Theo mức rủi ro |
| Security/static analysis | Có | Có |
| Cross-JDK tests | Theo support matrix | Theo support matrix |
| Performance | Nếu hot path đổi | Nếu implementation đổi |
| Data/rollback | Nếu state/protocol đổi | Nếu schema/serialization đổi |

Các ô là hướng dẫn phạm vi kiểm chứng, không phải kết quả PASS của một dự án.

### 33.1. Golden fixtures

Với codec và clients, có thể lưu một tập fixtures:

~~~text
fixtures/
  request-valid.json
  request-invalid.json
  response-legacy.json
  customer-record-v1.bin
  customer-record-v2.bin
~~~

Chúng giúp bảo vệ behavior qua thay thư viện/generator. Fixtures không được chứa secrets hoặc dữ liệu cá nhân thật; nếu cần dữ liệu đại diện, dùng dữ liệu giả được kiểm soát.

### 33.2. Cross-version tests

Trong giai đoạn rolling deployment:

- Client cũ ↔ server mới.
- Client mới ↔ server cũ.
- Writer mới ↔ reader cũ.
- Writer cũ ↔ reader mới.
- Consumer dùng JDK khác nhau nếu có MRJAR/generated bytecode variants.

Không thể kết luận chỉ từ compilation của generated DTO rằng hợp đồng đa phiên bản vẫn an toàn.

## 34. Tình huống: generated code vẫn import javax

Giả sử handwritten source đã chuyển sang:

~~~java
import jakarta.validation.Valid;
~~~

nhưng generated client vẫn có:

~~~java
import javax.validation.Valid;
~~~

Nguyên nhân có thể:

1. Recipe chỉ áp vào handwritten sources.
2. Generator cũ vẫn tạo Java EE imports.
3. Config chưa bật Jakarta target.
4. Stale output hoặc build cache.
5. CI và local dùng generator versions khác nhau.
6. Template tùy biến chưa được cập nhật.

Hướng xử lý: xác định owner/generator, cập nhật version/options/template, regenerate, review diff, compile và test validation behavior. Không sửa generated Java bằng tay rồi chờ lần build tiếp theo ghi đè.

## 35. Tình huống: generator đổi 300 files nhưng schema giữ nguyên

Một migration cập nhật generator version và CI báo:

~~~text
300 Java files modified
25 files renamed
10 files deleted
~~~

Các bước phân tích:

1. Xác minh schema và templates/checksums gốc.
2. Xác nhận generator version/config đã đổi có chủ đích.
3. Phân nhóm imports, generated comments, formatting, types, API signatures và file moves.
4. Tắt hoặc tách timestamp/line-ending noise.
5. Kiểm tra classes/methods bị xóa.
6. So API/wire/schema contracts.
7. Chạy tests và client/server compatibility checks.
8. Ghi rõ những thay đổi chấp nhận được.
9. Nếu diff vượt review capacity, tách upgrade generator khỏi schema change.

Không dùng `git diff --ignore-space-change` như lời giải thích thay cho semantic review.

## 36. Tình huống: CI xanh nhưng generated files stale

Nếu repo commit `src/generated/java`, developer sửa `orders.yaml` nhưng quên chạy generator, source cũ vẫn compile và unit tests có thể pass.

Freshness gate giải quyết bằng cách:

1. Checkout sạch.
2. Chạy pinned generator.
3. So tracked outputs với HEAD.
4. Kiểm tra untracked outputs mới.
5. Fail CI khi output không khớp.
6. Cung cấp diff để developer regenerate và commit.

Tuy nhiên, gate chỉ chứng minh **output khớp input/toolchain**, không chứng minh schema mới tương thích đối tác. Cần contract tests riêng.

## 37. Quy trình migration từ Java 11/Spring Boot 2 lên Java 17/Spring Boot 3

Ví dụ kế hoạch nhiều giai đoạn:

### Pha A — Đóng baseline

- Ghi JDK, framework/BOM, build tools, generator versions.
- Lưu input schemas, generated outputs và test evidence.
- Khóa repository state.

### Pha B — Chuẩn bị toolchain

- Chuyển compiler/test JVM sang Java 17 theo support policy.
- Nâng annotation processors, JaCoCo, bytecode/static tools nếu cần.
- Xác minh generator có thể chạy/reproduce output.

### Pha C — Mechanical rewrite

- Áp recipe chuyển các nhóm API cần thiết sang Jakarta theo phạm vi module.
- Không đổi Java SE `javax.*`.
- Review diff và dependency graph.

### Pha D — Regenerate

- Chọn generator/template phù hợp Jakarta.
- Trước tiên giữ schema không đổi nếu có thể.
- Kiểm tra generator-only diff.
- Sau đó thay schema có chủ đích và review contract diff.

### Pha E — Kiểm chứng

- Compile, unit/integration tests.
- Validation/security-negative tests.
- API/serialization golden fixtures.
- Contract tests qua các service versions.
- Generated freshness/CI reproducibility.
- Artifact/class-file/runtime checks.

### Pha F — Triển khai

- Canary/rolling deployment khi phù hợp.
- Theo dõi logs, 4xx/5xx, DB errors, metrics và traces.
- Đảm bảo rollback binary và data compatibility.

Từng pha cần owner và evidence; kết thúc một recipe không phải kết thúc Java migration.

## 38. Những anti-pattern phải tránh

### 38.1. Thay text không có type scope

Đổi tất cả `javax.` thành `jakarta.` có thể phá Java SE APIs. Ưu tiên type-aware rules.

### 38.2. Không pin recipe/generator

Cùng source có thể sinh code khác do tool release thay. Đưa exact versions vào build/config.

### 38.3. Sửa tay generated file

Lần regenerate sau sẽ ghi đè. Sửa schema, template hoặc generator options.

### 38.4. Chạy nhiều migration lớn một lúc

Không biết lỗi đến từ JDK, framework, serializer hay generator. Tách nguyên nhân khi có thể.

### 38.5. Coi diff rỗng là generator đúng

Generated outputs có thể bị ignore, task có thể skip hoặc cache stale.

### 38.6. Bỏ qua untracked files

`git diff` không tự thấy file mới chưa track. CI gate cần xét chúng nếu generated outputs được commit.

### 38.7. Bỏ qua timestamp noise

Nếu mỗi lần generate tạo hàng nghìn diff nhiễu, reviewer dễ bỏ qua thay đổi API quan trọng. Sửa generator config/format policy.

### 38.8. Chỉ xem source diff mà bỏ schema/wire contract

Một thay đổi field number hoặc required field có thể làm client không tương thích dù Java source diff ít.

### 38.9. Xóa tests hoặc hạ security rules để build xanh

Đó là bỏ cơ chế kiểm soát, không phải chứng minh migration đúng.

### 38.10. Không có rollback data plan

Source có thể revert nhưng dữ liệu do version mới ghi vẫn tồn tại; cần compatibility window và kế hoạch rollback.

## 39. Mẫu báo cáo automation và generated diff

~~~yaml
migrationChange:
  project: orders-service
  baselineCommit: record-commit-id
  targetJdk: "17"
  mechanicalRewrite:
    tool: OpenRewrite
    version: record-exact-version
    recipes:
      - com.example.migration.UseJakartaEntity
    scope:
      - src/main/java
    dryRunReviewed: false
    secondRunNoDiff: false
  generation:
    sourceOfTruth:
      - api/orders.yaml
    generator: OpenAPI Generator
    version: record-exact-version
    templatesChecksum: record-checksum
    outputTrackedInGit: true
    outputPath: src/generated/java
    deterministicVerified: false
    generatedDiffReviewed: false
  contracts:
    publicApiReviewed: false
    wireSchemaReviewed: false
    dataCompatibilityReviewed: false
  validation:
    compilePassed: false
    unitTestsPassed: false
    integrationTestsPassed: false
    securityReviewPassed: false
  deployment:
    rolloutPlan: pending
    rollbackPlan: pending
  owner: application-team
  status: in-progress
~~~

Mẫu chỉ có mục đích trình bày. Không tự chuyển các trường `false` thành `true` nếu chưa có bằng chứng test thực tế.

## 40. Checklist khi hoàn thành một đợt automation

- [ ] Baseline commit, JDK và dependency graph đã ghi rõ.
- [ ] Phân loại mechanical/semantic/generated changes.
- [ ] Recipe/tool/generator version được pin.
- [ ] Đã chạy và review dry-run diff ở phạm vi chính xác.
- [ ] Không có blanket Javax/Jakarta replace gây ảnh hưởng Java SE APIs.
- [ ] Recipe được kiểm tra idempotency khi phù hợp.
- [ ] Generated files có source of truth và owner rõ.
- [ ] Generator có inputs/config/templates tái lập.
- [ ] Timestamps/locale/line endings và nhiễu được xử lý.
- [ ] Với generated files được commit: đã kiểm tra tracked/untracked diff.
- [ ] Với generated files bị ignore: đã kiểm tra snapshots/artifacts.
- [ ] Public API, schema và wire contracts được review.
- [ ] Không còn stale generated output hoặc cache errors.
- [ ] Unit/integration/contract/security tests cần thiết đã chạy.
- [ ] Runtime JDK và class-file version được xác minh.
- [ ] Deployment artifact được đối chiếu với source đã test.
- [ ] PR có giải thích thay đổi kỳ vọng/ngoài dự kiến.
- [ ] Rollout và rollback bao gồm cả dữ liệu khi cần.

Checklist là hướng dẫn kỹ thuật, **không phải chứng nhận repository đã chạy QA**.

## 41. Nguyên tắc tổng kết

- **Tự động hóa phần cơ học, không thay thế đánh giá ngữ nghĩa.** Rename API có thể tự động, nhưng behavior phải được kiểm chứng.
- **AST/type-aware refactoring an toàn hơn text replacement tổng quát** đối với các thay đổi Java API có phạm vi rõ.
- **Recipe cần scope, preconditions, version pin và idempotency** để chạy lặp lại đáng tin.
- **Mã sinh phải được quản lý từ schema, template, annotation processor và generator configuration**, không sửa trực tiếp outputs không có kế hoạch.
- **Generator determinism và correctness là hai câu hỏi khác nhau.** Cùng output chưa chắc đúng; output thay chưa chắc là bug.
- **Git diff không thấy mọi generated files**: tracked, untracked và ignored outputs có chiến lược kiểm tra khác nhau.
- **Diff nhỏ có thể gây breaking change lớn** nếu ảnh hưởng Protobuf field numbers, HTTP methods, DTO nullability, SQL types hoặc security metadata.
- **Javax/Jakarta migration phải nhận diện đúng API owner**, giữ các Java SE packages `javax.net.ssl`, `javax.sql` và những package tương ứng.
- **OpenAPI, Protobuf, Avro, jOOQ, MapStruct và các annotation processors có hợp đồng riêng** cần kiểm thử đúng định dạng.
- **Build cache, toolchain, locale và generator versions ảnh hưởng output**, nên CI cần inputs và môi trường có thể tái lập.
- **Generated diff phải được giải thích theo nhóm thay đổi**, gồm tool-only, formatting, API và dữ liệu.
- **Kiểm chứng bằng compile, contract, integration và security tests**, đồng thời có owner và rollback plan khi thay runtime/data.

Trong **Java Advance Compatibility Migration**, tự động hóa là công cụ để chuẩn hóa các bước chỉnh sửa lặp lại và giảm sai sót, không phải bằng chứng ứng dụng đã tương thích. Khi kết hợp recipes có giới hạn, source of truth rõ ràng, generator được pin, diff checks trên cả tracked/ignored outputs và tests theo hợp đồng, nhóm có thể nâng JDK và framework mà vẫn hiểu được **mỗi thay đổi bắt nguồn từ đâu, tác động điều gì và sẽ được phát hiện bằng cách nào nếu sai**.
