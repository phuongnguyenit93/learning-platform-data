# Kiểm thử mã nguồn bằng cách biên dịch lại bên sử dụng

Khi nâng JDK, nâng phiên bản thư viện hoặc thay đổi public API của một module Java, câu hỏi quan trọng không chỉ là **“thư viện mới có biên dịch được không?”** mà còn là **“mã nguồn của những ứng dụng đang sử dụng thư viện đó có biên dịch lại được mà không phải sửa không?”**. Đây là trọng tâm của **kiểm thử tương thích mã nguồn** (*source compatibility testing*) bằng cách biên dịch lại bên sử dụng, thường gọi là *consumer recompilation* hoặc *downstream compilation test*.

Một thư viện có thể tự build thành công và vượt qua mọi unit test nội bộ nhưng vẫn phá vỡ hàng chục ứng dụng khác. Ví dụ, tác giả thư viện đổi kiểu trả về từ `String` sang `Optional<String>`, thêm một overload khiến lời gọi cũ trở nên mơ hồ, thay đổi giới hạn generic hoặc ngừng export một package trong `module-info.java`. Các thay đổi này có thể chỉ lộ ra khi **compiler xử lý lại source thực tế của consumer** với artifact mới.

Bài học thuộc chương **Kiểm thử hồi quy** của module **Java Advance Compatibility Migration**. Nội dung trình bày cách xác định phạm vi consumer, dựng thí nghiệm compile có đối chứng giữa phiên bản cũ và mới, kiểm soát JDK/toolchain/dependency graph, phân loại lỗi, tự động hóa trong CI và kết hợp với kiểm thử binary/runtime để đưa ra kết luận tương thích có cơ sở.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt **source compatibility**, **binary compatibility** và **behavioral compatibility**.
- Giải thích vì sao build thành công của thư viện mới không chứng minh consumer source vẫn tương thích.
- Thiết kế phép thử giữ nguyên consumer source và chỉ thay artifact thư viện để phát hiện lỗi biên dịch do nâng cấp.
- Xác định các kiểu thay đổi API thường phá vỡ source: chữ ký method, kiểu trả về, visibility, overload, generics, checked exceptions, interface và JPMS.
- Sử dụng Maven hoặc Gradle để biên dịch consumer với artifact cũ/mới trên cùng điều kiện kiểm thử.
- Phân biệt lỗi do API với lỗi do JDK, compiler, transitive dependencies, annotation processors và cấu hình build.
- Tổ chức **consumer corpus**, test fixture, ma trận JDK và báo cáo regression.
- Biết các giới hạn của recompilation test và những phép kiểm thử bổ sung cần thiết trước khi phát hành.

## 2. Source compatibility khác binary và behavioral compatibility

### 2.1. Source compatibility

**Source compatibility** trả lời câu hỏi:

> Nếu giữ nguyên mã nguồn của consumer, có thể biên dịch nó bằng compiler/toolchain đã chọn với phiên bản thư viện mới hay không?

Ví dụ consumer:

```java
package com.example.consumer;

import com.example.api.UserDirectory;

public final class UserScreen {
    public String display(long id) {
        UserDirectory directory = new UserDirectory();
        String name = directory.findName(id);
        return "Xin chào " + name;
    }
}
```

Ở phiên bản thư viện cũ, `findName(long)` trả về `String`. Phiên bản mới trả về `Optional<String>`:

```java
// API cũ
public String findName(long id);

// API mới
public Optional<String> findName(long id);
```

Nếu consumer source không đổi, phép gán vào `String` sẽ thất bại khi biên dịch với thư viện mới. Đây là một **source compatibility break** có thể quan sát trực tiếp.

### 2.2. Binary compatibility

**Binary compatibility** trả lời một câu hỏi khác:

> Nếu consumer đã được biên dịch với thư viện cũ, class file đó có còn liên kết và chạy được với thư viện mới mà không cần biên dịch lại không?

Một consumer JAR đã biên dịch có những tham chiếu bytecode nhất định tới class/method/field. Nếu thư viện mới xóa method hoặc thay descriptor không tương thích, khi chạy có thể gặp:

```text
java.lang.NoSuchMethodError
java.lang.NoClassDefFoundError
java.lang.IncompatibleClassChangeError
java.lang.IllegalAccessError
```

Những lỗi này thường xuất hiện ở runtime, không phải lúc compiler xử lý lại consumer source.

**Không được kết luận “binary compatible” chỉ vì consumer source biên dịch lại thành công.** Một thay đổi có thể cho phép compile source mới nhưng khiến class file cũ liên kết không đúng. Ngược lại, có thay đổi giữ binary compatibility nhưng phá vỡ source compatibility.

### 2.3. Behavioral compatibility

**Behavioral compatibility** hỏi:

> Consumer sau nâng cấp có tiếp tục có kết quả, exception, transaction, serialization và hành vi vận hành đúng contract không?

Ví dụ một thư viện vẫn giữ chữ ký:

```java
public int calculateDiscount(int amount);
```

nhưng đổi quy tắc làm tròn hoặc trả về giá trị khác khi `amount = 0`. Source compilation và bytecode linking đều có thể thành công, nhưng nghiệp vụ bị phá vỡ.

Để phát hiện loại này cần regression, integration, contract hoặc property-based tests.

### 2.4. Ma trận ba lớp tương thích

| Loại tương thích | Đối tượng thử | Phép kiểm tra | Không chứng minh được |
| --- | --- | --- | --- |
| Source | Mã nguồn consumer giữ nguyên | Compile lại với API mới | Binary cũ tiếp tục chạy; hành vi đúng |
| Binary | Class/JAR consumer được build trước nâng cấp | Chạy hoặc phân tích ABI với library mới | Consumer source mới chắc chắn compile |
| Behavioral | Luồng nghiệp vụ và contract | Unit/integration/contract/load tests | Mọi lời gọi source của các consumer khác compile |
| Configuration/deployment | Build và runtime thực | Start/test với toolchain/container thật | Tính đúng đắn của mọi kết quả nghiệp vụ |

Trong Java compatibility migration, những lớp kiểm thử này **bổ sung cho nhau**, không thay thế nhau.

## 3. Vì sao phải biên dịch chính bên sử dụng?

### 3.1. Unit tests của thư viện chỉ kiểm tra những trường hợp tác giả viết

Thư viện có thể có test coverage cao nhưng không sử dụng những cách gọi mà consumer thực tế đang dùng:

- Consumer truyền `null` cho một overload.
- Consumer định nghĩa class implement interface của thư viện.
- Consumer dùng subclass hoặc override protected method.
- Consumer phụ thuộc vào generic type inference rất cụ thể.
- Consumer dùng method reference, lambda hoặc annotation processor.
- Consumer nằm trong named module và tham chiếu package được export.
- Consumer import một kiểu public nhưng không được coi là API hỗ trợ chính thức.

Những patterns đó thường không xuất hiện trong test suite của nhà cung cấp thư viện. **Recompile consumer source** đưa compiler qua các call sites thực sự mà ứng dụng phụ thuộc.

### 3.2. Phân tích API diff là cần nhưng chưa đủ

Công cụ API/ABI diff có thể báo rằng method bị xóa, visibility đổi hoặc generic signature khác. Tuy nhiên, tác động source còn phụ thuộc vào **cách consumer sử dụng API**.

Ví dụ thêm overload có thể trông như thay đổi cộng thêm, nhưng lại làm lời gọi consumer trở nên mơ hồ. Ngược lại, một API bị xóa chưa chắc phá consumer cụ thể nếu consumer không dùng nó.

Do đó nên kết hợp:

1. API diff để tìm thay đổi có rủi ro.
2. Consumer recompilation để đo **impact thực tế lên source đang sử dụng**.
3. Runtime tests để xác nhận behavior và binary compatibility.

### 3.3. Khi nào đặc biệt cần recompilation test?

Rất hữu ích khi:

- Nâng major/minor version của thư viện dùng chung trong mono-repo hoặc nhiều repository.
- Thay public API của một internal SDK.
- Di chuyển từ JDK 8 lên 11/17/21 cùng với thay đổi dependency.
- Nâng framework core/BOM và extension APIs.
- Chuyển `javax.*` sang `jakarta.*`.
- Chuyển thư viện từ classpath sang module path.
- Nâng compiler hoặc thay Java source level.
- Thay đổi generic bounds, overloads hoặc interface methods.
- Xuất bản một thư viện có nhiều downstream consumers, đặc biệt khi cam kết source compatibility.

## 4. Phạm vi kiểm thử: đâu là “bên sử dụng”?

### 4.1. Consumer trực tiếp

Consumer trực tiếp khai báo dependency tới thư viện và dùng những kiểu public trong source.

```text
library-api
     |
     +----> web-service
     +----> batch-job
     +----> desktop-client
```

Khi nâng `library-api`, tối thiểu cần biên dịch source của những consumer quan trọng này với artifact mới.

### 4.2. Consumer gián tiếp

Một module có thể không import class của library trực tiếp nhưng bị ảnh hưởng vì một dependency bắc cầu đổi version hoặc public API của module trung gian chứa kiểu thuộc thư viện đó.

```text
shared-model
    |
    v
business-sdk
    |
    v
order-service
```

Nếu `business-sdk` công khai method trả về kiểu từ `shared-model`, nâng `shared-model` có thể buộc `order-service` compile lại và điều chỉnh source.

Không nên chỉ dựa vào direct imports để xác định phạm vi; cần xét public API exposure và transitive dependency graph.

### 4.3. External consumers

Đối với thư viện được phát hành cho đối tác, không phải mọi source consumer đều nằm trong repository của nhà cung cấp.

Có thể xây dựng **consumer corpus** gồm:

- Sample applications chính thức.
- Integration tests được khách hàng đồng ý cung cấp.
- Adapter hoặc SDK của những đối tác quan trọng.
- Ví dụ API công khai từ tài liệu.
- Một số downstream open-source projects có license và quyền truy cập phù hợp.
- Các compatibility fixtures thể hiện patterns từng gây regression.

Kết quả chỉ chứng minh khả năng compile của **corpus đã kiểm thử**, không chứng minh mọi consumer bên ngoài đều tương thích.

### 4.4. Consumer của generated code

Mã bên sử dụng không chỉ là source do người viết:

- Java source sinh từ OpenAPI/Protobuf/gRPC.
- MapStruct/annotation processors.
- JPA metamodel.
- Framework code generation.
- Kotlin/Groovy/Scala modules gọi Java library.
- Bytecode generation hoặc runtime proxy.

Với generated code, cần tái sinh từ **generator version và schema thực tế**, rồi compile cả output. Một fixture chỉ chứa generated code cũ có thể bỏ sót lỗi generator không còn hiểu API đích.

## 5. Thiết kế phép thử đối chứng chuẩn

### 5.1. Giữ nguyên source consumer

Quy tắc quan trọng nhất: để phát hiện tác động của library upgrade, hãy **giữ nguyên snapshot source của consumer** và chỉ đổi dependency artifact.

```text
                        Consumer source S (cố định)
                                   |
                     +-------------+-------------+
                     |                           |
                     v                           v
          Library v1 + môi trường E      Library v2 + môi trường E
                     |                           |
                     v                           v
              Compile baseline             Compile candidate
                     |                           |
                     +-------------+-------------+
                                   |
                                   v
                           So sánh diagnostics
```

Môi trường E gồm JDK/compiler, source level, build tool, plugin, các dependency khác, annotation processors và cấu hình classpath/module path.

Nếu thay cả source consumer, JDK và library trong cùng lần chạy, không thể kết luận lỗi được gây bởi thay đổi nào.

### 5.2. Hai kết quả phải được đọc cùng nhau

| Baseline v1 | Candidate v2 | Diễn giải |
| --- | --- | --- |
| PASS | PASS | Không phát hiện source break trong corpus và môi trường đã chọn. |
| PASS | FAIL | **Source compatibility regression** có khả năng do candidate; cần phân loại lỗi. |
| FAIL | PASS | Source từng không compile trên baseline; có thể API mới sửa được, nhưng baseline cần được giải thích. |
| FAIL | FAIL | Thí nghiệm không có baseline đáng tin hoặc source vốn đã lỗi; không được kết luận candidate tạo regression. |

Với phép thử nghiêm ngặt, chỉ nên coi `PASS→FAIL` là tín hiệu regression sau khi xác nhận artifact và environment chỉ khác đúng yếu tố được thử.

### 5.3. Hai loại phép thử cần tách

**Phép thử A – library compatibility:** giữ nguyên JDK/toolchain, chỉ thay library version. Mục đích tìm source breaks do library.

**Phép thử B – Java migration compatibility:** giữ consumer source và library version trong tổ hợp được hỗ trợ, đổi JDK/`--release`. Mục đích tìm breaks do Java source/API/module system.

Cuối cùng mới thử **tổ hợp đích JDK mới + library mới**. Việc tách phép thử giúp tìm nguyên nhân nhanh hơn.

### 5.4. Không coi artifact trong local cache là bằng chứng đủ

Phải ghi nguồn gốc artifact:

- Group ID, artifact ID, version.
- Repository nội bộ/public và checksum.
- Build commit hoặc release tag nếu là snapshot.
- Packaging/classifier.
- Các transitive dependencies thực sự đã resolve.
- Module name/descriptor nếu chạy trên module path.

Nếu `1.0-SNAPSHOT` bị ghi đè giữa hai lượt build, phép thử “cùng version” có thể dùng hai bộ bytecode khác nhau. Nên dùng artifact bất biến hoặc publish vào repository thử nghiệm cô lập.

## 6. Ví dụ cơ bản: library đổi kiểu trả về

### 6.1. API của thư viện trước khi nâng

Giả sử thư viện `com.example:directory-api:1.0.0` có:

```java
package com.example.directory;

public final class UserDirectory {
    public String findName(long userId) {
        return "User-" + userId;
    }
}
```

Consumer code:

```java
package com.example.consumer;

import com.example.directory.UserDirectory;

public final class UserPage {
    private final UserDirectory directory = new UserDirectory();

    public String title(long id) {
        String name = directory.findName(id);
        return "Welcome, " + name;
    }
}
```

Biên dịch với API cũ: hợp lệ.

### 6.2. API candidate sau thay đổi

Thư viện `2.0.0` đổi method thành:

```java
package com.example.directory;

import java.util.Optional;

public final class UserDirectory {
    public Optional<String> findName(long userId) {
        return Optional.of("User-" + userId);
    }
}
```

Khi compile **chính source `UserPage` cũ** với thư viện mới, compiler có thể báo:

```text
incompatible types:
java.util.Optional<java.lang.String> cannot be converted to java.lang.String
```

Đây là bằng chứng trực tiếp rằng API mới phá vỡ source compatibility của consumer đang có.

### 6.3. Hai chiến lược xử lý

**Chiến lược 1 – Giữ tương thích ở thư viện:** giữ `String findName(long)` trong một giai đoạn và thêm method mới có tên khác, ví dụ `Optional<String> findNameOptional(long)`. Sau đó deprecate method cũ theo lộ trình.

**Chiến lược 2 – Migration có chủ đích:** chấp nhận breaking change và cập nhật source của consumer:

```java
public String title(long id) {
    String name = directory.findName(id).orElse("Unknown");
    return "Welcome, " + name;
}
```

Cần ghi rõ rằng code consumer **đã sửa** biên dịch thành công là phép thử migration readiness, **khác** với kết luận source compatibility của API mới đối với consumer chưa sửa.

## 7. Những thay đổi API dễ gây source break

### 7.1. Xóa hoặc đổi tên class/method/field

```java
// v1
public void registerUser(String id);

// v2
public void createUser(String id);
```

Consumer gọi `registerUser` sẽ compile fail nếu không có adapter hoặc method cũ.

Điều tương tự xảy ra khi xóa constructor public, đổi tên type, ngừng export package, hoặc làm class/constructor không còn visible.

### 7.2. Thay parameter types

```java
// v1
public void send(String destination);

// v2
public void send(Endpoint destination);
```

Lời gọi `send("queue-A")` có thể không còn hợp lệ. Nếu `Endpoint` có constructor nhận `String`, compiler **không tự biến đổi** một `String` thành `Endpoint` trừ khi có conversion được ngôn ngữ cho phép.

Nếu API đích giữ overload tương thích, consumer có thể vẫn compile. Kết quả phụ thuộc chữ ký cụ thể.

### 7.3. Đổi kiểu trả về

```java
// v1
public List<Order> findOrders();

// v2
public Stream<Order> findOrders();
```

Consumer gán trực tiếp vào `List<Order>` hoặc gọi `size()` sẽ compile fail.

Đổi return type cũng có thể tác động binary linking. Cần kiểm tra riêng source và binary compatibility; không suy rằng chỉ do method name không đổi thì ABI không đổi.

### 7.4. Thêm checked exception

```java
// v1
public void flush();

// v2
public void flush() throws java.io.IOException;
```

Nếu consumer gọi `flush()` từ method không khai báo/catch `IOException`, compiler sẽ báo unhandled exception.

Trái lại, thay unchecked exception hoặc đổi hành vi throw có thể không gây compile failure nhưng vẫn là behavioral regression.

### 7.5. Đổi visibility

```java
// v1
public class Validator {
    public boolean check(String input) { return true; }
}

// v2 - ví dụ thay đổi API gây break
public class Validator {
    protected boolean check(String input) { return true; }
}
```

Consumer ngoài package không phải subclass phù hợp không còn gọi `check` theo cách cũ.

Không chỉ xem class public hay không; một method có thể chịu ảnh hưởng của **package visibility, subclass context, module exports và Java access rules**.

### 7.6. Thay đổi generics

Ví dụ:

```java
// v1
public List<Number> numbers();

// v2
public List<Integer> numbers();
```

Dù `Integer` là subtype của `Number`, `List<Integer>` **không** là subtype của `List<Number>` do Java generics invariance. Consumer:

```java
List<Number> values = api.numbers();
```

có thể compile với v1 nhưng fail với v2.

Cần xem cả:

- Generic type parameter.
- Bounds như `<T extends Number>`.
- Wildcard `? extends` và `? super`.
- Return type của fluent API.
- Generic inheritance và type inference.
- Raw types, warnings và unchecked conversions.

Một thay đổi signature sau type erasure có thể ảnh hưởng source nhưng không nhất thiết thay JVM descriptor theo cách giống nhau. Do đó source và binary compatibility vẫn phải được đo riêng.

### 7.7. Thêm overload gây mơ hồ

Thêm method mới trông như thay đổi **không phá vỡ**, nhưng đôi khi làm lời gọi cũ không thể chọn overload.

Ví dụ v1:

```java
public void register(CharSequence value);
```

v2 thêm:

```java
public void register(java.io.Serializable value);
```

Consumer vẫn gọi:

```java
api.register("alice");
```

`String` implement cả `CharSequence` và `Serializable`. Hai overload nhận các kiểu tham số không có quan hệ subtype với nhau, nên lời gọi có thể bị compiler báo **reference to register is ambiguous**.

Đây là lý do một API diff chỉ báo “new method added” chưa đủ để khẳng định source-compatible.

### 7.8. Method reference và lambda

Consumer có thể viết:

```java
Function<String, Result> operation = service::process;
```

Thêm overload, thay generics hoặc thay functional interface target có thể khiến type inference thay đổi hoặc lời gọi mơ hồ, dù các method dùng trong source trông rất đơn giản.

Consumer recompilation đặc biệt hữu ích cho những use case khó suy ra tác động chỉ từ danh sách method.

### 7.9. Interface và default methods

Một interface được thêm abstract method có thể làm class của consumer implement interface đó không còn compile (nếu class concrete chưa triển khai method mới).

Thêm **default method** có thể giữ nhiều consumer hoạt động, nhưng không phải lúc nào cũng source-compatible: nếu class implement hai interface nay đều cung cấp default method có cùng chữ ký, compiler có thể yêu cầu class override để xử lý xung đột.

Ví dụ khái niệm:

```java
interface A {
    default String label() { return "A"; }
}

interface B {
    // v1: chưa có label()
    // v2: thêm default String label() { return "B"; }
}

class ConsumerType implements A, B {
    // v1 compile; v2 có thể bị yêu cầu override label()
}
```

Cần compile các class consumer **implement/extend API**, không chỉ code trực tiếp gọi API.

### 7.10. `static`, instance members và constructor

Chuyển từ method static sang instance (hoặc ngược lại) ảnh hưởng cách gọi. Đổi constructor public sang factory method khiến mã `new Type(...)` không compile.

Đồng thời kiểm tra những API có thể được kế thừa: thêm method `final` hoặc đổi superclass có thể phá các subclass của consumer.

### 7.11. Enum, sealed types, records

Khi framework/library tiến hóa cùng Java, có thể xuất hiện:

- Enum có thêm constant: source compile thường vẫn được, nhưng switch hoặc logic nghiệp vụ có thể cần cập nhật.
- Sealed hierarchy: class consumer từng extends/implements có thể bị cấm do `permits` hoặc hạn chế module/package.
- Record/class conversion: constructor, accessor, inheritance hoặc reflection contract có thể thay đổi.
- Pattern matching/switch features phụ thuộc Java source level: consumer source có thể không compile với `--release` cũ.

Kết luận phải dựa trên **phiên bản ngôn ngữ và cách consumer sử dụng API**.

### 7.12. Annotation API và generated code

Consumer có thể khai báo annotation của library trên source, hoặc dùng annotation processor sinh mã gọi một API.

Nếu thay tên annotation element, retention/target, required element hoặc generator output, lỗi có thể xuất hiện khi compile hoặc ở giai đoạn annotation processing.

Một phép thử chỉ compile source đã có generated files nhưng không chạy processor có thể bỏ sót vấn đề. Cần dùng pipeline phát sinh source giống consumer thực tế.

## 8. Java version: cùng source nhưng khác compiler và `--release`

### 8.1. Source compatibility luôn có ngữ cảnh

Không thể nói “thư viện tương thích mã nguồn” mà không ghi:

- JDK vendor/version và compiler sử dụng.
- `--release` hoặc source/target compatibility.
- Bộ dependency và module path/classpath.
- Compiler options, annotation processors và warnings policy.
- Đặc điểm source consumer (Java/Kotlin/Groovy...).
- Version module/JAR của candidate.

Một source dùng `var`, records hoặc một language feature khác có thể compile ở một mức Java và fail ở mức thấp hơn bất kể library version có đổi hay không.

### 8.2. `--release` kiểm soát Java API level

Ví dụ:

```bash
javac --release 11 \
  -cp libs/directory-api-2.0.0.jar \
  -d out \
  src/com/example/consumer/UserPage.java
```

`--release 11` giúp compiler hạn chế source/target API Java SE theo release 11. Nhưng nó **không tự kiểm tra** rằng mọi thư viện bên thứ ba trong classpath đều dùng bytecode và API tương thích với runtime Java 11.

Cần kiểm tra Java baseline của các dependency và chạy thử artifact trên JVM đích.

### 8.3. Không thay JDK khi đang đo riêng API break

Nếu muốn so v1/v2 của library, thực hiện hai compile trên **cùng JDK và cùng compiler flags**. Nếu nâng JDK cũng là mục tiêu, làm thí nghiệm JDK riêng trước/sau để không nhầm nguyên nhân.

Một matrix có thể như sau:

| Consumer source | Library | Compiler/`--release` | Mục tiêu |
| --- | --- | --- | --- |
| S0 | v1 | JDK 17 / release 11 | Baseline |
| S0 | v2 | JDK 17 / release 11 | Source compatibility |
| S0 | v1 | JDK 21 / release 11 | Kiểm tra ảnh hưởng JDK/compiler |
| S0 | v2 | JDK 21 / release 11 | Cấu hình ứng dụng mục tiêu |

Đây là ví dụ. Nếu v1 không hỗ trợ chạy/build trên JDK 21, ghi rõ ô đó không hợp lệ và chọn các bước so sánh được hỗ trợ.

### 8.4. JDK mới có thể lộ phụ thuộc API nội bộ

Một consumer dùng `sun.*` hoặc `jdk.internal.*` có thể bị compile/access error khi JDK mới siết module boundary. Lỗi này khác một API break của thư viện nghiệp vụ, dù đều xuất hiện trong lần recompile.

Khi phân loại, xác định class/method thuộc JDK module hay library candidate và kiểm tra `exports`/`requires` cùng compiler flags. Không nên chữa mọi lỗi bằng `--add-exports`.

## 9. Maven: dựng consumer recompilation test

### 9.1. Consumer fixture độc lập

Giả sử có hai artifact thư viện:

```text
com.example:directory-api:1.0.0
com.example:directory-api:2.0.0
```

Và một project consumer:

```text
consumer-compat/
├── pom.xml
└── src/
    └── main/java/com/example/consumer/UserPage.java
```

`pom.xml` khai báo version qua property để thay đổi artifact mà không sửa source:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example.testing</groupId>
  <artifactId>consumer-compat</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <api.version>1.0.0</api.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>directory-api</artifactId>
      <version>1.0.0</version>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

Ở cấu hình minh họa trên, property `api.version` chưa điều khiển dependency vì phiên bản đang được ghi cố định. Để cho phép chạy đối chứng, sửa **chỉ** dòng phiên bản của dependency thành một expression Maven property:

```xml
<version>&#36;{api.version}</version>
```

Cách dùng entity `&#36;` ở ví dụ văn bản là để hiển thị ký tự dollar trong tài liệu; trong file `pom.xml` thực tế, dòng cần là biểu thức Maven với dấu `$` trực tiếp ngay trước dấu ngoặc nhọn. Không đặt XML entity trong POM thật.

Với cách này, CI có thể chọn phiên bản artifact qua command line mà không phải sửa source.

### 9.2. Compile consumer với hai phiên bản

Maven commands:

```bash
# Baseline
mvn -Dapi.version=1.0.0 clean test-compile

# Candidate: cùng source, chỉ đổi version của API dependency
mvn -Dapi.version=2.0.0 clean test-compile
```

`test-compile` giúp compile cả main và test source mà **chưa chạy** tests. Nếu chỉ muốn đánh giá mã trong `src/main/java`, có thể dùng `clean compile`. Sau khi kiểm tra compile, vẫn cần chạy regression tests ở bước khác.

Thực tế nhiều consumer phụ thuộc một BOM/parent nên phiên bản có thể được kiểm soát bằng dependency management thay vì một property trực tiếp. Khi đó cần một cơ chế override có thể tái lập, bảo đảm **artifact cuối cùng thực sự là v1/v2** theo kết quả dependency resolution.

### 9.3. Vì sao phải `clean`?

Nếu build incremental hoặc output cũ còn trong `target/classes`, một số kết quả có thể không phản ánh source/artifact mới theo cách kỳ vọng. Compile lại từ trạng thái sạch giúp giảm nhiễu do cache.

Tuy nhiên, chạy `clean` không đảm bảo repository dependency cache đúng hoặc artifact bất biến. Phải xác minh version/checksum đã resolve trong mỗi lượt.

### 9.4. Dependency tree của consumer

Có thể xem:

```bash
mvn -Dapi.version=2.0.0 dependency:tree
```

Nếu candidate kéo một bản dependency bắc cầu không tương thích, compiler error có thể đến từ version của dependency đó chứ không phải API trực tiếp đã đổi.

Muốn kết luận chính xác, ghi cả:

- Direct candidate dependency.
- Transitive versions thay đổi.
- Parent/BOM version.
- Scope và optional dependencies.
- Plugin/processor dependencies.

Đừng giả định việc chỉ đổi một property không làm thay đổi graph khác.

### 9.5. Multi-module Maven và reactor

Nếu library candidate và consumer cùng thuộc một Maven reactor, dùng `-am` có thể khiến Maven build artifact **từ source trong reactor** thay vì dùng JAR đã phát hành mà bạn muốn kiểm tra.

Điều này không sai nếu mục đích là thử integration với source candidate, nhưng **không tương đương** thử một artifact release bất biến.

Có thể tách consumer fixture thành project riêng hoặc dùng local/remote test repository với artifact đã publish. Ghi rõ thí nghiệm đang so source checkout, snapshot build hay released JAR.

## 10. Gradle: compile consumer đối chứng

### 10.1. Chọn phiên bản dependency bằng project property

Ví dụ `build.gradle` theo Groovy DSL:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

def apiVersion = providers.gradleProperty('apiVersion')
        .orElse('1.0.0')
        .get()

dependencies {
    implementation 'com.example:directory-api:' + apiVersion
}
```

Cấu hình này minh họa cách giữ nguyên source và thay dependency bằng một property. Toolchain Java 17 là một ví dụ; dự án phải chọn Java release thực sự được hỗ trợ và cân nhắc `options.release` nếu cần nhắm Java thấp hơn.

### 10.2. Compile với hai artifact

```bash
# Baseline
./gradlew -PapiVersion=1.0.0 clean compileJava compileTestJava

# Candidate
./gradlew -PapiVersion=2.0.0 clean compileJava compileTestJava
```

Cần dùng đúng Gradle Wrapper được quản lý bởi repository. Nếu trên Windows, dùng `gradlew.bat` tương ứng.

Với codebase sử dụng Kotlin/Scala hoặc generated sources, bổ sung task compile và toolchain của ngôn ngữ tương ứng.

### 10.3. Kiểm tra phiên bản thực tế

```bash
./gradlew -PapiVersion=2.0.0 \
  dependencies --configuration compileClasspath

./gradlew -PapiVersion=2.0.0 \
  dependencyInsight \
  --dependency directory-api \
  --configuration compileClasspath
```

Version catalog, constraints, platform, dependency locking và resolution rules có thể tác động phiên bản được chọn. Không suy luận từ dòng `implementation` mà bỏ qua kết quả dependency resolution.

### 10.4. Compile path và runtime path có thể khác nhau

Một library có thể có API types phụ thuộc vào những artifact chỉ xuất hiện trong runtime scope hoặc bị đưa vào `compileOnly` không đúng.

Recompile consumer sẽ bộc lộ một số lỗi “thiếu kiểu trong public API” mà unit tests nội bộ của library không phát hiện, đặc biệt khi library từng build với classpath rộng hơn classpath mà consumer thực nhận.

Nên thử với **published metadata** (Maven POM, Gradle Module Metadata) và cách resolve dependency mà consumer production sử dụng.

## 11. Giữ phép thử sạch và có khả năng tái lập

### 11.1. Những điều kiện nên cố định

| Điều kiện | Cách kiểm soát |
| --- | --- |
| Consumer source | Pin commit/tag, không thay source giữa hai compile. |
| Compiler | Cùng JDK vendor/version và `--release` trong phép thử API. |
| Build tool | Dùng Maven/Gradle Wrapper/version được khóa. |
| Plugins | Pin compiler, annotation processor, language plugin versions. |
| Dependency khác | Lock/BOM hoặc ghi rõ graph để phân tích khác biệt. |
| Artifact candidate | Immutable coordinate/checksum, không ghi đè snapshot tùy ý. |
| Classpath/module path | Cùng chế độ và cấu hình, trừ thứ đang cố ý thử. |
| Cache/output | Build sạch hoặc đảm bảo task không dùng output cũ. |
| Environment | Ghi OS, architecture, env vars và profiles khi ảnh hưởng compile. |

### 11.2. Mức cô lập cần phù hợp

Có thể chạy hai lượt compile ở hai workspace/container riêng, mỗi lượt dùng repository cache có cơ chế kiểm soát rõ. Điều đó giúp tránh artifact candidate vô tình ghi đè baseline hoặc compiler incremental cache gây nhầm.

Không nhất thiết tạo hai repository độc lập cho mọi build nhỏ, nhưng đối với một release có nhiều consumer và yêu cầu audit, **tính tái lập quan trọng hơn tiết kiệm vài phút cache**.

### 11.3. Consumer source ở thời điểm nào?

Thường cần ít nhất hai corpus:

- **Current consumer source (S0):** code đang chạy production tại một commit đã chốt.
- **Migrated consumer source (S1):** code đã được chỉnh sửa để phù hợp candidate.

Thử S0 + library mới để đo **source compatibility**. Thử S1 + library mới để chứng minh **migration readiness**.

Nếu chỉ thử S1, ta có thể biết ứng dụng mới build được nhưng không biết phiên bản thư viện mới có phá vỡ consumer cũ hay không.

## 12. Kiểm thử JPMS và classpath/module path

### 12.1. `module-info.java` cũng là một phần contract

Consumer explicit named module có thể khai báo:

```java
module com.example.consumer {
    requires com.example.directory;
}
```

Nếu thư viện đổi module name, ngừng export package hoặc đổi vị trí JAR, consumer có thể compile fail dù class và method Java vẫn còn.

Đây là **source compatibility trong cấu hình modular**. Một test chỉ biên dịch library trên classpath có thể không phát hiện.

### 12.2. `requires transitive` và API exposure

Giả sử module A công khai API trả về một type thuộc module B. Một consumer C chỉ `requires A` có thể phụ thuộc vào việc A có `requires transitive B` hay không theo module graph.

Nếu phiên bản mới thay `requires transitive` thành `requires` thông thường, consumer C có thể mất readability với B và không compile trong một số cách sử dụng.

Khi kiểm thử JPMS, cần giữ đúng module descriptor và module path của consumer, không lặng lẽ chuyển về classpath để “bài test xanh”.

### 12.3. Automatic module và unnamed module

Một JAR chưa có descriptor có thể trở thành automatic module khi đặt trên module path, lấy tên từ `Automatic-Module-Name` hoặc tên file. Nếu tên module thay đổi, `requires` của consumer có thể fail.

Một JAR trên classpath thường thuộc unnamed module và có quy tắc visibility khác explicit named module. Vì vậy kết quả recompilation trên classpath không chứng minh kết quả trên module path và ngược lại.

### 12.4. `exports` khác `opens`

Source consumer import class từ package của named module yêu cầu package đó được export phù hợp. `opens` chỉ phục vụ reflective access theo contract JPMS, không thay thế ordinary source access.

Nếu compiler báo package “not visible”, cần điều tra `requires`, `exports` và module resolution; không thêm `--add-opens` như phản xạ mặc định.

### 12.5. Multi-release JAR

Một thư viện có thể chứa class khác nhau dưới `META-INF/versions/...`. JDK compiler/runtime khác nhau có thể chọn view tương ứng theo quy tắc multi-release JAR.

Nếu bảo đảm hỗ trợ nhiều JDK, thử các cấu hình thực sự trong matrix và kiểm tra artifact đã publish. Một lần compile trên JDK 21 không chứng minh consumer với JDK 11 thấy cùng API.

## 13. Tác động của dependency bắc cầu và BOM

### 13.1. Không thay thư viện trong khoảng chân không

Library v2 có thể nâng những dependency bắc cầu:

```text
Consumer
  |
  +-- directory-api v1 -> json-core v1
  |
  +-- directory-api v2 -> json-core v2
```

Một compiler error trong consumer có thể đến từ public API của `json-core` được lộ qua library, không nhất thiết từ một class nằm trong `directory-api`.

Cần ghi graph của **cả hai lượt**; nếu mục tiêu là đo tác động tổng thể của nâng dependency theo thực tế, đó vẫn là regression đáng quan tâm. Nếu muốn tách nguyên nhân, thêm một phép thử kiểm soát riêng.

### 13.2. BOM có thể che version override

Ứng dụng sử dụng Spring Boot hoặc platform BOM có thể không khai báo version trực tiếp của nhiều thư viện. Một property override ở consumer chưa chắc thắng các ràng buộc khác.

Sau khi thay candidate version, kiểm tra `dependency:tree` hoặc `dependencyInsight` để chắc chắn classpath thực sự chứa artifact mong muốn.

### 13.3. Exclusion và scope

Một artifact thiếu dependency ở compile scope có thể khiến consumer fail khi import một kiểu thuộc API, dù library tự compile được vì nó có dependency trong build local.

Kiểm thử consumer từ published artifact giúp phát hiện một số sai lệch giữa `pom.xml`/Gradle metadata được công bố và dependency graph tác giả thư viện từng dùng để build.

### 13.4. Shading và relocation

Nếu thư viện relocate một dependency, các kiểu trong public API hoặc annotation có thể đổi namespace. Consumer recompilation giúp thấy lỗi import, generic type hoặc assignability.

Nhưng reflection dùng `Class.forName`, `ServiceLoader` và metadata trong `META-INF/services` có thể chỉ hỏng runtime. Do đó vẫn cần tests khám phá provider và integration tests sau khi compile thành công.

## 14. Annotation processors và ngôn ngữ hỗn hợp

### 14.1. Processor là một phần môi trường consumer

Một source consumer có thể dựa trên Lombok, MapStruct, Dagger, AutoService, JPA metamodel hoặc processor riêng. Compiler có thể sinh những class/method cần thiết để mã còn lại compile.

Nếu nâng API library làm processor không hiểu annotation hoặc type signature, lỗi có thể nằm ở **generated source** chứ không ở source người viết.

Hãy chạy compile với processor giống consumer production, không tắt annotation processing chỉ để qua bước test.

### 14.2. Đổi annotation và contract generate

Ví dụ một annotation của thư viện:

```java
@GenerateAdapter(target = OldType.class)
public interface AccountMapper { }
```

Nếu `OldType` bị đổi tên, hoặc processor mới đòi một annotation element khác, compilation có thể fail ở annotation processing.

Khi sửa lỗi cần cập nhật nguồn annotation/template/generator. Không chỉnh generated Java file bằng tay rồi coi là migration hoàn tất, vì lần build sau có thể ghi đè.

### 14.3. Consumer Kotlin, Scala hoặc Groovy

Một thư viện Java có thể được gọi từ Kotlin/Scala/Groovy. Các ngôn ngữ này có quy tắc type inference, nullability, overload và compiler version khác Java.

Một corpus chỉ biên dịch Java source không thể chứng minh tương thích cho mọi consumer đa ngôn ngữ. Tốt hơn nên giữ test consumer đại diện bằng **compiler và build plugin thật** của từng ngôn ngữ được cam kết hỗ trợ.

### 14.4. Source được sinh khác source được phát hành

Nếu SDK được sinh từ OpenAPI, gRPC hoặc schema, có thể cần ba phép kiểm tra:

1. Generator cũ + schema cũ tạo ra source như baseline.
2. Generator/SDK mới + schema đích tạo source đúng.
3. Consumer source không thay đổi hoặc đã migration compile với generated API đích.

Chỉ compile một folder source generated được lưu sẵn không chứng minh generator hoạt động với dependency/JDK mới.

## 15. Compile consumer không thay thế runtime binary test

### 15.1. Thử với consumer binary cũ

Ngoài `S0 + library v2 -> compile`, tạo một test khác:

```text
Consumer binary B0 (đã compile với library v1)
                  |
                  v
        Runtime classpath dùng library v2
                  |
                  v
       Link + execute chức năng quan trọng
```

Phép thử này bắt được những lỗi chỉ xuất hiện với bytecode đã phát hành.

### 15.2. Vì sao recompilation có thể che binary break?

Compiler có thể tạo bytecode khác khi nhìn thấy API v2. Một client được biên dịch lại có thể chạy tốt, trong khi client cũ vẫn mang method descriptor từ v1 và gặp `NoSuchMethodError` ở runtime.

Ví dụ, thay return type hoặc method owner có thể làm compiler xử lý khác đi. Vì vậy nhà cung cấp thư viện cần biết **mình cam kết source compatibility, binary compatibility hay cả hai**.

### 15.3. API compatibility tools

Một số công cụ Java thường dùng để phân tích API/ABI diff là **japicmp**, **Revapi**, **Clirr** hoặc những phép phân tích `javap`/`jdeps` phù hợp.

Chúng có giá trị cho việc sàng lọc thay đổi public API và một số dạng binary/source incompatibility, nhưng không thể đại diện toàn bộ cách compiler thực xử lý source consumer, nhất là với overload resolution, generics inference, processor và ngữ cảnh JDK riêng.

Kết hợp API diff với consumer recompilation để có phạm vi phát hiện tốt hơn.

### 15.4. Runtime test cần cùng artifact đã qua compile gate

Một lỗi quy trình phổ biến là compile consumer với artifact candidate A, nhưng integration test hoặc production deploy lại dùng artifact B do SNAPSHOT bị ghi đè, cache hoặc BOM override.

Giữ artifact identity/checksum thống nhất qua build, test, package và deploy. Khi cần thử binary compatibility, dùng consumer binary cố định và chỉ thay runtime library theo kế hoạch.

## 16. Tránh báo lỗi giả khi recompile

### 16.1. Compiler/toolchain khác nhau

Nếu lượt baseline dùng JDK 11 còn lượt candidate dùng JDK 21, warning/error có thể đến từ Java language changes hoặc option khác.

Cách xử lý: chạy đối chứng cùng compiler; dùng một matrix riêng cho JDK migration.

### 16.2. Dependency graph thay đổi ngoài phạm vi

Một BOM mới có thể nâng cả JSON, logging hoặc validation dependency. Nếu consumer fail, ghi rằng **tổ hợp dependency mới gây lỗi**, rồi dùng thêm các bước phân tích để tìm thành phần liên quan.

Không được tuyên bố API library v2 tự nó gây break khi chưa phân tích graph.

### 16.3. Test vốn đã đỏ từ baseline

Nếu code consumer không compile với v1 do lỗi source, configuration hoặc artifact thiếu, phép thử v2 fail không thể coi là một regression mới.

Phải sửa hoặc ghi nhận baseline blocker trước, và phân loại từng lỗi theo lịch sử.

### 16.4. Output/cache còn lại

Build incremental có thể giữ generated class hoặc kết quả compile cũ. Dùng clean build hoặc môi trường cách ly phù hợp.

Đồng thời tránh dùng cache artifact mutable với cùng version. Tên version không chứng minh bytecode bất biến.

### 16.5. Profile hoặc feature flags khác nhau

Source sets, Maven profiles, Gradle configurations, conditional compilation và optional modules có thể làm hai lượt compile chọn tập file khác nhau.

Ghi lại effective profile/configuration; nếu không, so sánh kết quả hai tập source khác nhau không có ý nghĩa.

### 16.6. Network/repository lỗi

Một lượt compile fail vì không tải được artifact không phải source compatibility failure. Phân loại riêng:

- Artifact unavailable.
- Repository/authentication/network issue.
- Dependency resolution conflict.
- Plugin/toolchain failure.
- Java compilation diagnostic.
- Annotation processing failure.

Chỉ nhóm lỗi thực sự do source/API nên được đưa vào thống kê source breaks.

## 17. Phân loại kết quả compiler theo nguồn gốc

| Triệu chứng | Khả năng nguyên nhân | Điều tra |
| --- | --- | --- |
| `cannot find symbol` với method/type | API bị xóa/đổi tên; dependency thiếu. | So API diff, source call site và graph. |
| `incompatible types` | Return type/generics/parameter thay đổi. | So chữ ký v1/v2 và type inference. |
| `reference to ... is ambiguous` | Overload mới hoặc generic inference đổi. | Xem candidate overloads và kiểu đối số. |
| `unreported exception ... must be caught` | Method thêm checked exception. | So `throws` clause và call site. |
| `has private access` / không visible | Visibility hoặc JPMS `exports` thay đổi. | So modifiers, module graph và package. |
| `does not override abstract method` | Interface thêm abstract method. | Xem implementer trong consumer. |
| `inherits unrelated defaults` | Interface default methods xung đột. | Xem tất cả superinterfaces. |
| `class file has wrong version` | Compiler/JDK thấp hơn class file của dependency. | So Java baseline, test/compiler JVM. |
| `package ... does not exist` | Dependency scope, module path hoặc namespace đổi. | Kiểm tra classpath, Jakarta migration, BOM. |
| Annotation processing error | Processor/generator không tương thích. | So processor version, generated source và JDK. |
| `module not found` | Module name/path/resolution đổi. | Kiểm tra `module-info.java` và module descriptor của JAR. |
| Repository resolution failure | Artifact chưa publish hoặc quyền truy cập. | Kiểm tra repository/checksum, không quy lỗi API. |

Một compiler message không phải bản báo cáo root cause hoàn chỉnh. Thường cần **đọc location và dependency của call site** để xác định chính xác thay đổi API liên quan.

## 18. Đo “mức độ ảnh hưởng” khi có nhiều consumer

### 18.1. Không chỉ đếm lỗi compiler thô

Một thay đổi API duy nhất có thể tạo ra hàng trăm diagnostic cascading. Ví dụ đổi `findName` khiến nhiều lớp khác compile fail do type không còn đúng.

Thay vì chỉ báo “320 compile errors”, nên tổng hợp:

- Số consumer project bị ảnh hưởng.
- Số source file/call site bị ảnh hưởng.
- Số **API changes gốc** gây break.
- Độ nghiêm trọng theo sản phẩm và SLA.
- Khả năng có adapter giữ tương thích.
- Công sức migration của các consumer quan trọng.

### 18.2. Phân loại theo mức rủi ro

| Mức | Mô tả | Hướng xử lý |
| --- | --- | --- |
| Blocker | Consumer production quan trọng không compile và không có migration được chấp thuận. | Chặn release hoặc bổ sung compatibility shim. |
| High | Nhiều consumer cần sửa API hoặc toolchain, có khả năng ảnh hưởng lịch triển khai. | Lập kế hoạch migration và xác minh từng consumer. |
| Medium | Consumer ít dùng hoặc có migration cơ học rõ ràng. | Cung cấp guide/recipe và test. |
| Low | API deprecated nhưng source còn compile; có thể cần chuyển trong tương lai. | Ghi nhận lộ trình và cảnh báo. |

Không dùng các nhãn như “High” thay cho đánh giá nghiệp vụ. Một breaking change ở consumer nhỏ nhưng có dữ liệu tài chính vẫn có thể nghiêm trọng.

### 18.3. Tiêu chí không giảm coverage

Nếu corpus ban đầu có 40 consumer mà lần candidate chỉ chạy 12 consumer vì job CI bị skip, kết quả PASS không đáng tin.

Nên ghi:

- Consumer được dự kiến.
- Consumer thực sự được compile.
- Consumer bị skip và lý do.
- Baseline PASS/FAIL.
- Candidate PASS/FAIL.
- Phiên bản artifact và environment.

Quality gate phải fail hoặc yêu cầu phê duyệt khi **phạm vi kiểm thử bị giảm ngoài kế hoạch**.

## 19. Dựng consumer corpus có giá trị

### 19.1. Chọn consumer đại diện

Không nhất thiết lấy mọi dự án ngay từ ngày đầu; có thể ưu tiên:

- Consumer sử dụng nhiều public APIs.
- Consumer quan trọng trong production.
- Consumer dùng subclassing/implementation của library interfaces.
- Consumer dùng Java/Kotlin/Scala trong những ngữ cảnh khác nhau.
- Consumer ở các Java source levels còn được hỗ trợ.
- Consumer modular và classpath-based.
- Consumer dùng annotation processor, framework integration hoặc generated SDK.
- Consumer sử dụng những APIs đang deprecated hoặc dự định thay đổi.

### 19.2. Ghi snapshot và quyền sở hữu

Mỗi consumer entry nên có:

```text
Consumer ID:
Repository/project:
Commit/tag:
Primary language:
JDK/compiler/--release:
Build tool/version:
Framework/BOM:
Dependency coordinates:
Classpath/module path:
Owner:
Critical APIs used:
Baseline compile result:
Candidate compile result:
Evidence link/log:
```

Đối với external repositories, cần lưu rõ revision và giấy phép/điều kiện sử dụng nếu copy source vào test fixture nội bộ.

### 19.3. Consumer fixtures cho những API khó

Ngoài full consumer apps, có thể tạo một số **minimal source fixtures**:

- Overload ambiguity với `null`, lambda hoặc method reference.
- Generic bounds và wildcard.
- Interface implementation/default method conflict.
- Subclass override/protected API.
- Checked exceptions.
- Named module `requires`/`exports`.
- Annotation processor generated client.
- Public API lộ transitive dependency type.

Minimal fixtures chạy nhanh, dễ chẩn đoán; full consumer corpus giúp phát hiện tương tác thực tế và configuration khác biệt.

## 20. Tích hợp vào CI/CD

### 20.1. Pipeline tối thiểu

Một pipeline cho library candidate có thể gồm:

```text
Build library candidate
       |
       v
Publish candidate artifact bất biến vào repository thử nghiệm
       |
       v
Lấy consumer source snapshots đã chốt
       |
       +--> Compile với baseline library v1
       |
       +--> Compile với candidate library v2
       |
       v
So sánh pass/fail và compiler diagnostics
       |
       v
Tổng hợp impacted APIs / consumer owners
       |
       v
Release gate / migration plan
```

Khi build library candidate và consumer cùng repository, cần tránh lỗi tình cờ dùng project dependency source thay vì candidate artifact được kiểm thử. Ghi rõ cách pipeline resolve dependency.

### 20.2. Parallelism và isolation

Có thể chạy compile nhiều consumer song song để giảm thời gian. Nhưng các job nên tránh ghi vào cùng output directory hoặc mutable local Maven repository theo cách dễ gây race/đổi snapshot.

Mỗi job cần có artifact identity, compiler version và reports riêng. Không được ghi đè kết quả PASS của một consumer bằng lần compile của consumer khác.

### 20.3. Kết quả job nên có trạng thái rõ

```text
BASELINE_PASS
CANDIDATE_PASS
SOURCE_BREAK
BASELINE_BROKEN
ENVIRONMENT_ERROR
DEPENDENCY_RESOLUTION_ERROR
SKIPPED_APPROVED
SKIPPED_UNEXPECTED
```

Không quy mọi non-zero exit code thành `SOURCE_BREAK`. Nếu artifact không tải được hoặc compiler crash, đó là lỗi hạ tầng hoặc tooling cần điều tra riêng.

### 20.4. Kiểm soát exception/waiver

Một breaking change có thể được chấp nhận trong major release. Khi đó, hồ sơ release cần ghi:

- API bị thay và lý do.
- Danh sách consumer bị ảnh hưởng.
- Migration guide hoặc compatibility shim.
- Owner và mốc triển khai.
- Test xác minh consumer **đã sửa** compile và chạy được.
- Điều kiện rollback hoặc thời hạn hỗ trợ phiên bản cũ.

Waiver không đồng nghĩa “kết quả test source compatibility là PASS”. Nó nghĩa là break đã được nhận diện và chấp nhận theo chính sách release.

## 21. Một tình huống end-to-end trong mono-repo

### 21.1. Cấu trúc

```text
enterprise-platform/
├── billing-api/
├── billing-client/
├── order-service/
├── reporting-batch/
└── compatibility-fixtures/
```

`billing-api` là thư viện dùng chung. `billing-client` và hai service tiêu thụ API trực tiếp hoặc gián tiếp.

### 21.2. Thay đổi candidate

Ở `billing-api` v2, nhóm phát triển:

- Đổi `createInvoice(String)` thành `createInvoice(CustomerId)`.
- Thêm một overload `send(CharSequence)` và một overload khác `send(Serializable)`.
- Thêm checked exception ở method `flush()`.
- Đổi một DTO generic từ `List<Number>` sang `List<Integer>`.
- Bỏ export một package trong module descriptor.

Những thay đổi có thể gây break cho các consumer khác nhau.

### 21.3. Lộ trình kiểm tra

**Giai đoạn A:** compile snapshot consumer với v1 và lưu kết quả baseline. Nếu có consumer lỗi sẵn, đưa vào danh sách blocker riêng.

**Giai đoạn B:** compile cùng snapshots với v2, giữ JDK/compiler và dependency graph trong phạm vi được kiểm soát.

**Giai đoạn C:** phân loại compiler errors theo API break thay vì report hàng trăm diagnostics không nhóm.

**Giai đoạn D:** quyết định API nào cần compatibility shim, API nào chấp nhận breaking change với hướng dẫn migration.

**Giai đoạn E:** tạo nhánh migrated consumer source và compile với v2; chạy unit/integration/security/contract tests.

**Giai đoạn F:** thử consumer binary cũ với runtime v2 nếu sản phẩm có cam kết hỗ trợ binary client đã phát hành.

### 21.4. Ví dụ bảng kết quả

| Consumer | v1 source compile | v2 source compile | Nhóm nguyên nhân | Quyết định |
| --- | --- | --- | --- | --- |
| billing-client | PASS | FAIL | Signature `CustomerId` | Thêm adapter hoặc sửa client |
| order-service | PASS | FAIL | Overload ambiguity | Điều chỉnh API hoặc call site |
| reporting-batch | PASS | PASS | Không dùng API đã thay | Tiếp tục runtime regression tests |
| modular-consumer | PASS | FAIL | Package không còn export | Xem lại module API contract |

Các kết quả là minh họa. Báo cáo thật phải đính kèm compiler diagnostics, exact artifact versions và commit IDs.

### 21.5. Điều kiện phát hành

Không nên kết luận “tất cả consumers đã tương thích” nếu chỉ một số consumer trong corpus pass. Một phát hành có kiểm soát cần nêu rõ:

- Source compatibility đã giữ được hay có breaking changes chấp nhận.
- Consumer nào đã migration.
- Consumer nào còn chờ.
- Binary compatibility được kiểm tra đến đâu.
- Runtime/behavioral tests đã chạy.
- Version support và rollback plan.

## 22. Thực hành: ba lỗi compiler khác nhau

### Bài tập A: thêm overload

Thư viện cũ:

```java
public final class Formatter {
    public void format(CharSequence value) { }
}
```

Thư viện mới thêm:

```java
public void format(java.io.Serializable value) { }
```

Consumer:

```java
formatter.format("hello");
```

Câu hỏi: đây là lỗi runtime hay compile? Vì sao một method mới thêm vẫn có thể phá source compatibility?

**Gợi ý:** `String` thuộc cả hai kiểu không có quan hệ subtype với nhau; overload resolution có thể mơ hồ khi biên dịch lại.

### Bài tập B: thêm checked exception

V1:

```java
void write() { }
```

V2:

```java
void write() throws java.io.IOException { }
```

Consumer:

```java
public void process() {
    writer.write();
}
```

Câu hỏi: vì sao consumer compile fail với v2? Có cần sửa code của thư viện hay của consumer, hay nên giữ method cũ theo chính sách API?

**Gợi ý:** compiler kiểm tra checked exceptions trong chữ ký; quyết định sửa nằm ở cam kết compatibility và migration plan.

### Bài tập C: source compile nhưng binary cũ có thể hỏng

V1:

```java
public String status() { return "OK"; }
```

V2 thay bằng:

```java
public Object status() { return "OK"; }
```

Consumer mới:

```java
Object result = api.status();
```

Câu hỏi: việc consumer source mới compile với v2 có chứng minh một JAR consumer cũ đã biên dịch với method trả `String` vẫn liên kết được không?

**Đáp án định hướng:** Không. Cần thử binary client cũ và/hoặc dùng ABI diff; bytecode method descriptor có thể thay đổi khi return type thay đổi.

## 23. Checklist cho một lượt consumer recompilation

### Phạm vi

- [ ] Đã xác định tên/version nguồn và đích của library.
- [ ] Đã biết cam kết source compatibility áp dụng cho consumer nào.
- [ ] Đã có source snapshots của direct/indirect consumers quan trọng.
- [ ] Đã bao phủ language levels, named modules và build configurations được hỗ trợ.
- [ ] Đã có fixtures cho generics, overload, subclass, interface và processor nếu liên quan.

### Điều kiện thử

- [ ] Giữ nguyên consumer source giữa baseline/candidate.
- [ ] Kiểm soát JDK/compiler/`--release`, plugins và dependency graph.
- [ ] Đã dùng đúng artifact bất biến, xác minh version/checksum.
- [ ] Đã kiểm tra classpath/module path và dependency scopes.
- [ ] Đã dọn build output hoặc cô lập cache đủ để không dùng class cũ.
- [ ] Đã xác nhận cả main source và test/generated source theo phạm vi thử.

### Báo cáo

- [ ] Baseline v1 compile PASS hoặc đã ghi blocker có lý do.
- [ ] Candidate v2 compile và lưu đầy đủ diagnostic.
- [ ] Phân loại lỗi source/API khác lỗi hạ tầng/toolchain/resolution.
- [ ] Ghi consumer owners và affected call sites.
- [ ] Gộp diagnostics trùng về các API changes gốc.
- [ ] Ghi rõ consumer bị skip và không giảm corpus không giải thích.

### Các phép kiểm tra bổ sung

- [ ] Đã xem API diff và khả năng binary compatibility.
- [ ] Đã thử consumer binary cũ nếu có cam kết ABI.
- [ ] Đã chạy unit/integration/contract tests cho migrated consumers.
- [ ] Đã kiểm tra Java/JDK support matrix và toolchain runtime.
- [ ] Đã kiểm tra reflection, SPI, serialization và service metadata nếu liên quan.
- [ ] Đã có migration guide, adapter hoặc waiver cho breaking changes chấp nhận.
- [ ] Đã cập nhật CI quality gate và lưu bằng chứng cho release.

## 24. Các hiểu lầm thường gặp

**“Library build thành công thì mọi consumer cũng build được.”** Không. Library thường không có đầy đủ các call site, subclass và annotation của consumer.

**“ABI diff không báo lỗi thì source chắc chắn tương thích.”** Không. Thêm overload hoặc đổi generic information có thể phá việc biên dịch mà không được phản ánh đơn giản qua binary descriptors.

**“Recompile consumer pass nghĩa thư viện mới không có bug.”** Không. Nó chỉ kiểm tra khả năng compile của source corpus trong môi trường đã chọn; cần test hành vi và runtime.

**“Đổi JDK và dependency trong cùng job rồi thấy fail nghĩa dependency mới hỏng.”** Không thể suy ra. Phải tách ảnh hưởng compiler/JDK và artifact.

**“Chỉ cần tìm chữ import là biết consumer nào phụ thuộc.”** Không đủ. Consumer có thể gọi API qua inheritance, generic types, annotation processors, reflection hoặc public API transitive.

**“Compile source đã sửa với v2 là đã chứng minh source compatibility.”** Không. Đó là phép thử migration readiness; source compatibility kiểm tra **source chưa sửa**.

**“Chỉ test các app trong mono-repo là bao phủ mọi khách hàng.”** Không. External consumers có thể dùng API theo cách khác; cần ghi phạm vi đã kiểm thử và các giới hạn.

**“Consumer source compile tốt thì JAR cũ chắc chắn chạy tốt với library mới.”** Không. Phải kiểm tra binary compatibility và runtime linking riêng.

**“Tests run: 0 nhưng build success nghĩa migration đã được kiểm thử.”** Không. Compile gate, test discovery và runtime regression tests là các phép kiểm tra độc lập.

## 25. Kết luận

**Kiểm thử mã nguồn bằng cách biên dịch lại bên sử dụng** là một kỹ thuật hồi quy có sức mạnh đặc biệt khi nâng Java, framework và thư viện dùng chung: nó biến những thay đổi API trừu tượng thành câu trả lời cụ thể về **source consumer đang tồn tại có còn compile hay không**. Phép thử tốt giữ nguyên snapshot source, cố định compiler/toolchain và những dependency ngoài phạm vi, rồi đối chiếu kết quả khi thay library v1 bằng v2.

Tuy nhiên, một lượt recompile không chứng minh binary client cũ vẫn chạy hoặc behavior nghiệp vụ không đổi. Trong Java Advance Compatibility Migration, cần kết hợp **consumer recompilation, API/ABI analysis, runtime binary tests và regression/contract tests**, lưu evidence cùng artifact/commit/JDK chính xác, và quản lý từng breaking change bằng migration guide hoặc adapter có chủ đích. Chỉ như vậy kết luận về tương thích mới có giá trị đối với cả tác giả thư viện lẫn những hệ thống đang phụ thuộc vào nó.
