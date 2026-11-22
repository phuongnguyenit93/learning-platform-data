# Phân biệt số phiên bản phát hành với bằng chứng tương thích thực tế

Trong một dự án **Java Advance Compatibility Migration**, số phiên bản giúp nhận diện một bản phát hành, nhưng **không tự chứng minh** ứng dụng, thư viện hoặc nền tảng dùng chung sẽ hoạt động tương thích. Nhìn thấy thư viện đổi từ `2.4.1` lên `2.4.2`, từ `2.4` lên `2.5`, hoặc thấy một JDK được gắn nhãn LTS chỉ cho ta một tín hiệu về cách nhà phát hành quản lý sản phẩm. Đó không phải kết quả kiểm thử các consumer cụ thể.

Tính tương thích phải được xác nhận bằng **bằng chứng có phạm vi**: mã nguồn consumer còn biên dịch được không, bytecode cũ còn liên kết được không, hành vi hợp đồng có giữ nguyên không, runtime và dependency có phù hợp không, dữ liệu/configuration có còn đọc được không, và thử nghiệm có phản ánh điều kiện triển khai thực tế không. Bằng chứng đáng tin cậy luôn đi kèm phiên bản chính xác, môi trường, bước thực hiện, kết quả và giới hạn của phép thử.

Bài này hướng dẫn cách đọc versioning mà không suy diễn quá mức và cách xây dựng hồ sơ bằng chứng tương thích để quyết định có thể nâng cấp an toàn hay cần kế hoạch migration.

## 1. Số phiên bản phát hành biểu thị điều gì?

Một số phiên bản (release version) chủ yếu trả lời câu hỏi **“đây là bản phát hành nào?”**. Tùy hệ sinh thái và chính sách của nhà cung cấp, nó còn có thể truyền đạt mức thay đổi dự kiến, trạng thái thử nghiệm, nhánh bảo trì hoặc mức cập nhật.

Ví dụ với tọa độ Maven/Gradle:

~~~text
com.example:customer-api:2.4.1
com.example:customer-api:2.5.0
com.example:customer-api:3.0.0
~~~

Ba artifact có thể dùng chung group và tên thư viện nhưng khác version. Con số không cho biết một ứng dụng cụ thể có gọi API đã bị thay đổi, có trùng dependency hay có cần JDK mới hơn không.

Một chuỗi phiên bản cũng không nhất thiết có cùng ý nghĩa trong mọi sản phẩm:

- Thư viện có thể dùng Semantic Versioning (SemVer).
- Sản phẩm khác có thể dùng năm/tháng phát hành, ví dụ `2026.11`.
- Bản phát hành có thể có suffix như `-RC1`, `-beta` hoặc `-SNAPSHOT`.
- JDK có các feature release, update release và build number riêng.
- Nền tảng nội bộ có thể dùng mã release train kết hợp phiên bản của nhiều thành phần.

Muốn diễn giải đúng, cần đọc **chính sách versioning của chính artifact đó**, không áp một quy tắc từ dự án khác.

## 2. SemVer là một cam kết phát hành, không phải bằng chứng kiểm thử

Semantic Versioning thường sử dụng cấu trúc `MAJOR.MINOR.PATCH`. Theo ý nghĩa thông dụng của SemVer khi được áp dụng nghiêm túc cho một API công khai đã xác định:

| Thành phần | Ý định phát hành | Điều không thể suy ra chỉ từ con số |
|---|---|---|
| MAJOR | Có thay đổi không tương thích với API công khai | Consumer cụ thể sẽ hỏng; hoặc mọi API cũ đều bị xóa |
| MINOR | Bổ sung tính năng tương thích ngược theo hợp đồng đã công bố | Mọi lời gọi cũ, overload, SPI và hành vi đều đã được kiểm chứng |
| PATCH | Sửa lỗi tương thích ngược theo hợp đồng đã công bố | Không có thay đổi hành vi ở trường hợp biên; không thể phát sinh regression |

Ví dụ, `2.4.1` → `2.4.2` là một patch release nếu dự án áp dụng SemVer. Điều này thể hiện **ý định** rằng API được hỗ trợ vẫn tương thích, nhưng để xác nhận một hệ thống thực tế, vẫn phải kiểm tra thay đổi và chạy bằng chứng phù hợp.

Một sửa lỗi có thể thay đổi hành vi từng bị implementation xử lý sai. Consumer vô tình dựa vào hành vi sai đó có thể bị ảnh hưởng. Ngược lại, một major release có thể có những API hoàn toàn không đổi; consumer chỉ dùng các API ấy có thể nâng cấp dễ dàng sau khi kiểm tra.

### 2.1. Giới hạn khi áp dụng SemVer

- SemVer chỉ có ý nghĩa đầy đủ nếu dự án xác định rõ **public API** và tuân thủ chính sách.
- Ở giai đoạn `0.y.z`, dự án có thể áp dụng quy tắc ổn định khác; cần xem tài liệu của dự án.
- Prerelease như `3.0.0-rc.1` không nên mặc định có cùng cam kết ổn định với bản chính thức.
- `SNAPSHOT` hoặc phiên bản động có thể đại diện cho nội dung thay đổi theo thời gian; cùng chuỗi version chưa chắc tái lập cùng binary nếu quy trình xuất bản không cố định artifact.
- Một số dự án không dùng SemVer, nên không thể mặc định `2.5.0` là bản “chỉ thêm chức năng”.
- Nhà cung cấp có thể mắc lỗi khi phân loại release. Việc ghi “patch” không sửa được một API break đã xuất hiện.

**Nguyên tắc:** versioning giúp ưu tiên mức độ kiểm tra; nó không thay thế kiểm tra.

## 3. Java SE, bản phân phối JDK và thư viện có những hệ phiên bản riêng

Trong migration Java, rất dễ gộp nhiều loại “version” vào một dòng duy nhất:

| Đối tượng | Ví dụ | Ý nghĩa chính |
|---|---|---|
| Java SE feature release | Java 17, 21, 25 | Mức ngôn ngữ, API và nền tảng Java tiêu chuẩn |
| JDK update/build | `21.0.x+build` | Một bản cập nhật/build của JDK cụ thể |
| JDK distribution/vendor | Oracle JDK, Eclipse Temurin, Amazon Corretto… | Nguồn build, đóng gói, cập nhật và chính sách hỗ trợ |
| Framework/library | `customer-api:2.5.0` | Phiên bản artifact theo chính sách thư viện |
| Build tool/plugin | Phiên bản Gradle, Maven hoặc plugin | Khả năng chạy build, API plugin và hỗ trợ JDK |
| Ứng dụng | Release `2026.11` | Tập hợp mã, cấu hình, schema và dependency được triển khai |

Hai ứng dụng dùng Java 21 có thể khác framework, dependency, cấu hình GC, OS và JDK vendor. Hai JDK cùng feature release vẫn có thể khác bản vá, OS/architecture được hỗ trợ hoặc cách đóng gói. Nhãn **LTS** là thông tin về chính sách hỗ trợ của nhà cung cấp hoặc nhánh phát hành, không chứng minh một ứng dụng chạy đúng trên JDK đó.

Khi lập bảng tương thích, ghi riêng **Java baseline**, **JDK thực dùng**, **distribution**, **library version**, **dependency graph** và **môi trường triển khai**.

## 4. Tương thích là một tập hợp nhiều chiều

Một tuyên bố “compatible” không đủ rõ nếu thiếu đối tượng và loại tương thích. Các chiều quan trọng gồm:

| Chiều | Câu hỏi phải trả lời | Ví dụ bằng chứng |
|---|---|---|
| Source compatibility | Source consumer cũ có biên dịch với thư viện mới không? | Compile consumer với API mới bằng compiler/target đã định |
| Binary compatibility | Bytecode consumer cũ có liên kết với JAR mới không? | Chạy consumer đã biên dịch từ trước trên JAR mới |
| Behavioral compatibility | Giá trị, exception, ordering, side effect có còn đúng hợp đồng không? | Contract test với các case có/không có dữ liệu, lỗi và cạnh biên |
| Runtime compatibility | Class file, JVM, module, native dependency có phù hợp không? | Test trên JDK/OS/architecture/container mục tiêu |
| Dependency compatibility | Dependency trực tiếp và bắc cầu có thể cùng tồn tại không? | Dependency graph, resolution check, integration test |
| Build-time compatibility | Compiler, Gradle/Maven, plugin, annotation processor còn chạy không? | Build trên toolchain dự kiến, kiểm tra task/output |
| Data/protocol compatibility | Schema, JSON, serialization, event và dữ liệu cũ có được đọc đúng không? | Consumer/producer contract test, schema compatibility test |
| Configuration/operational compatibility | Property, default, logging, startup, GC, TLS có còn phù hợp không? | Deploy smoke test, vận hành trên cấu hình đại diện |

Một API có thể **binary compatible nhưng behavioral incompatible**. Một ứng dụng có thể **source compatible nhưng không chạy được trên JDK tối thiểu** vì dependency đòi bytecode cao hơn. Do đó không nên trình bày một kết quả duy nhất “PASS” cho mọi chiều.

### 4.1. Xác định cặp đối tượng trước khi nói tương thích

Cần viết một phát biểu có thể kiểm chứng:

> “Consumer A đã biên dịch với customer-api 2.4.1 được chạy không cần biên dịch lại với customer-api 2.5.0 trên JDK 17, Linux x64, trong tập contract test X.”

Phát biểu này cụ thể hơn “customer-api 2.5.0 tương thích ngược”. Nó nêu rõ consumer, bản trước, bản sau, runtime và tập bằng chứng. Không được mở rộng kết luận vượt khỏi phạm vi đã kiểm tra.

## 5. Thêm API mới vẫn có thể gây source incompatibility

Giả sử phiên bản cũ chỉ có một overload:

~~~java
public final class Formatter {
    public static String format(String value) {
        return value == null ? "<none>" : value;
    }
}
~~~

Consumer cũ dùng:

~~~java
String text = Formatter.format(null);
~~~

Nhà cung cấp phát hành bản minor, thêm overload:

~~~java
public static String format(Integer value) {
    return value == null ? "<none>" : value.toString();
}
~~~

Sau thay đổi, câu lệnh `Formatter.format(null)` có thể trở nên **ambiguous** vì String và Integer không có quan hệ subtype với nhau. Binary đã biên dịch trước đó có thể vẫn tham chiếu method `format(String)` và chạy được, nhưng consumer biên dịch lại thất bại.

Bản phát hành có thể được đánh số MINOR theo chủ ý “chỉ thêm API”, song bằng chứng compile consumer lại cho thấy source incompatibility cho trường hợp này.

Những tình huống bổ sung API cần đánh giá gồm:

- Thêm overload ảnh hưởng null, lambda, method reference hoặc generic inference.
- Thêm method trừu tượng vào interface khiến implementor cũ không biên dịch.
- Thêm default method tạo xung đột giữa những interface được implement.
- Thêm method vào superclass có thể ảnh hưởng method cùng tên ở subclass.
- Thêm public type làm lộ dependency chưa có trên compile classpath.
- Thêm enum constant có thể tác động logic xử lý đầy đủ các trường hợp enum.
- Thay đổi annotation hoặc cơ chế scan ảnh hưởng code generation, reflection.

Không thể dùng riêng số MINOR để kết luận tất cả các consumer cũ đều source-compatible.

## 6. Thay đổi chữ ký method: nhìn số phiên bản không thấy lỗi liên kết

Giả sử phiên bản 1 của thư viện:

~~~java
package com.example.api;

public final class CustomerApi {
    public String find(String id) {
        return id;
    }
}
~~~

Phiên bản 2 xóa `find(String)` và thay bằng:

~~~java
package com.example.api;

public final class CustomerApi {
    public String lookup(String id) {
        return id;
    }
}
~~~

Consumer biên dịch trên phiên bản 1:

~~~java
import com.example.api.CustomerApi;

public class ConsumerApp {
    public static void main(String[] args) {
        System.out.println(new CustomerApi().find("C-42"));
    }
}
~~~

Nếu consumer được **biên dịch lại** với JAR phiên bản 2, compiler báo không tìm thấy method `find`. Nếu giữ bytecode consumer cũ và thay JAR mới khi chạy, JVM có thể ném `NoSuchMethodError` khi lời gọi được thực hiện. Đây là hai bằng chứng khác nhau: source break và binary break.

Để thử với artifact thực tế, có thể làm trong môi trường kiểm thử:

~~~bash
# Build consumer trên API cũ
javac --release 17 -cp lib-v1.jar \
  -d consumer-classes src/ConsumerApp.java

# Không biên dịch lại consumer; thay runtime library
java -cp "consumer-classes:lib-v2.jar" ConsumerApp
~~~

Trên Windows, classpath dùng dấu chấm phẩy thay dấu hai chấm, ví dụ `"consumer-classes;lib-v2.jar"`. Tên JAR và source trong ví dụ là minh họa.

Lưu ý: phép thử này chỉ có giá trị khi chắc chắn **JAR mới đã thay thế JAR cũ**, không có bản cũ còn hiện diện ở nơi khác trong classpath/module path, và code path gọi method bị thay đổi thực sự được chạy.

## 7. Những thay đổi không biểu hiện qua chữ ký API

Một API diff không phát hiện hết behavioral change. Ví dụ phương thức:

~~~java
public List<Order> findOrders(String customerId);
~~~

Giữ nguyên chữ ký giữa hai phiên bản, nhưng phiên bản mới trả danh sách theo thời gian giảm dần thay vì tăng dần. Nếu hợp đồng trước đó cam kết thứ tự tăng dần, đây là behavioral incompatibility dù source và binary đều có thể vẫn hoạt động.

Các thay đổi tương tự:

- Null trước đây nghĩa là “không tìm thấy”, sau chuyển thành exception.
- Exception trước đây là `IOException`, sau được wrap thành `IllegalStateException`.
- Timeout mặc định đổi từ 3 giây sang 30 giây.
- Tên property cũ được bỏ nhưng không có alias.
- API thay đổi cơ chế retry và sinh thêm side effect.
- JSON thêm trường bắt buộc hoặc đổi đơn vị từ mili giây sang giây.
- Transaction boundary thay đổi, ảnh hưởng dữ liệu đã ghi khi có lỗi.
- Một bản sửa bảo mật siết kiểm tra certificate, cipher hoặc quyền reflection.

Nhiều thay đổi trong số này có thể là chủ đích đúng đắn. Điều cần xác nhận là **hợp đồng đã cam kết** và đường migration của consumer, thay vì mặc định “chữ ký giữ nguyên nghĩa là không có breaking change”.

## 8. Phân biệt metadata, tuyên bố và bằng chứng

Khi quyết định nâng cấp, cần phân biệt ba lớp thông tin.

**Metadata** mô tả artifact: tên, version, build number, commit, release date, JDK baseline và repository.

**Tuyên bố** của nhà cung cấp mô tả chính sách hoặc kỳ vọng: “backward compatible”, “Java 17 supported”, “LTS”, “patch release”, hoặc “no breaking changes”.

**Bằng chứng** cho thấy một phép kiểm tra cụ thể đã được thực hiện và ghi nhận kết quả: output compiler, test report, dependency lockfile, API diff, runtime log, schema compatibility result, hay kết quả chạy consumer đã biên dịch từ trước.

Ví dụ:

| Thông tin | Loại | Kết luận phù hợp |
|---|---|---|
| `customer-api 2.5.0` | Metadata | Xác định artifact cần kiểm |
| “2.5.0 is backward-compatible” | Tuyên bố | Là giả thuyết/điều kiện hỗ trợ cần đối chiếu |
| API diff cho thấy không xóa public method | Bằng chứng tĩnh | Giảm rủi ro ở một phần API surface |
| Consumer A biên dịch thành công với 2.5.0 | Bằng chứng source | A source-compatible với cấu hình đã dùng |
| Consumer A bytecode cũ chạy contract test với 2.5.0 | Bằng chứng binary và hành vi | Những đường test đã chạy không có lỗi quan sát được |
| Production canary có lỗi TLS | Bằng chứng vận hành tiêu cực | Không thể kết luận migration an toàn dù test build pass |

Cần dùng cả thông tin nhà cung cấp lẫn bằng chứng thực tế. Release notes và chính sách hỗ trợ là đầu vào quan trọng, nhưng chúng không thay thế kiểm thử trong bối cảnh consumer của tổ chức.

## 9. Bằng chứng phải có phạm vi và điều kiện tái lập

Một dòng “Tests passed” chưa đủ để đánh giá mức độ tin cậy. Hồ sơ bằng chứng nên trả lời:

1. **Đối tượng:** artifact nào, version nào, checksum hoặc commit nào?
2. **Consumer:** ứng dụng/module nào, source revision nào?
3. **Mục tiêu:** kiểm tra source, binary, behavior, runtime, build, data hay cấu hình?
4. **Môi trường:** JDK feature/update/vendor, OS, architecture, container và dependency graph?
5. **Phương pháp:** lệnh, test suite, đầu vào, dữ liệu và điều kiện kích hoạt?
6. **Kết quả:** pass/fail, số test, warning, log và artifact?
7. **Phạm vi chưa bao phủ:** API, data variant, consumer, code path hoặc nền tảng nào?
8. **Thời điểm:** kết quả được ghi nhận khi nào, trước hay sau cập nhật dependency?

Ví dụ một ghi nhận ngắn:

~~~yaml
evidence:
  id: customer-api-2_5_0-consumer-a-runtime17
  provider: com.example:customer-api:2.5.0
  previousProvider: com.example:customer-api:2.4.1
  consumer: consumer-a
  consumerCommit: "example-commit-id"
  javaRuntime: "17"
  os: linux-x64
  testSuite: customer-contract-tests
  result: PASS
  limitations:
    - no-windows-run
    - no-external-plugin-consumers
~~~

Đây chỉ là mẫu minh họa. Khi sử dụng thật, cần bổ sung JDK build, distribution, dependency lock state, đường dẫn report và checksum artifact theo nhu cầu tái lập.

Bằng chứng tốt không ngụ ý “không thể có lỗi”. Nó cho phép biết chính xác điều gì đã được kiểm chứng và điều gì vẫn cần kiểm tra.

## 10. Bằng chứng từ API diff: hữu ích nhưng chưa đầy đủ

Đối với thư viện Java, so sánh API trước/sau giúp nhận diện thay đổi lớp và method được publish. Có thể sử dụng công cụ như japicmp, Revapi hoặc các phương pháp dựa trên `javap` và metadata artifact.

Phân tích nên bao phủ:

- Public và protected class, interface, method, field, constructor.
- Thay đổi method descriptor, generic signature và visibility.
- Abstract/default method, superclass, interface hierarchy.
- Checked exceptions, annotation, constant hoặc enum khi ảnh hưởng consumer.
- Module export/open và API được tài liệu hóa ở ngoài bytecode.
- Dependency lộ ra trong chữ ký public.

Một số công cụ phân loại thay đổi theo binary/source compatibility dựa trên những quy tắc kiểm tra cụ thể. Cần đọc cấu hình và phạm vi kiểm tra của công cụ: liệu nó phân tích annotation, generic, default method, API nội bộ hay transitive dependencies không?

### 10.1. Kiểm tra thủ công một method với javap

Có thể quan sát public method và descriptor:

~~~bash
javap -classpath customer-api-2.4.1.jar \
  -public -s com.example.api.CustomerApi

javap -classpath customer-api-2.5.0.jar \
  -public -s com.example.api.CustomerApi
~~~

So sánh output giúp phát hiện một số khác biệt về descriptor. Nhưng việc phương thức có descriptor giống nhau không chứng minh hành vi giữ nguyên. Đồng thời, `javap` không thay thế kiểm thử ở consumer.

### 10.2. Kết quả âm tính không tự động chứng minh tương thích

“API diff không thấy breaking change” chỉ có nghĩa **theo phạm vi và quy tắc của phép so sánh ấy**, không tìm ra thay đổi được phân loại là breaking. Nó không loại trừ lỗi dữ liệu, runtime, reflection, native code hoặc thay đổi hành vi.

Tương tự, “jdeps không báo API nội bộ” không chứng minh không có reflection động hoặc truy cập native tới chi tiết JDK. Mỗi công cụ có giới hạn riêng phải được ghi nhận.

## 11. Bằng chứng từ consumer compile test

**Consumer compile test** biên dịch lại mã nguồn consumer cũ với artifact mới. Nó là phép thử trực tiếp cho source compatibility trong môi trường đã chọn.

Ví dụ với consumer A:

~~~bash
javac --release 17 \
  -cp customer-api-2.5.0.jar \
  -d out src/main/java/com/example/ConsumerA.java
~~~

Một phép thử thực tế phải kèm toàn bộ classpath cần thiết hoặc sử dụng build tool để quản lý dependency, annotation processor và generated source. Thiếu dependency làm kết quả lỗi biên dịch không còn phản ánh riêng thay đổi API.

Các trường hợp nên bao phủ:

- Caller sử dụng method, constructor hoặc field công khai.
- Lớp consumer kế thừa class hoặc implement SPI.
- Lambda/method reference, overload và generic usage.
- Annotation processor, mapper hoặc code generator.
- Cấu hình source set đặc biệt và test code.
- Các module chỉ được build bằng JDK/Gradle cũ hơn.

Compile test cho biết source có hợp lệ với compiler, release và dependency đang dùng. Nó không chứng minh ứng dụng chạy đúng hay một consumer chưa được biên dịch trong test vẫn an toàn.

## 12. Bằng chứng từ binary compatibility test

**Binary compatibility test** giữ nguyên bytecode consumer đã biên dịch với thư viện cũ rồi chạy hoặc liên kết với thư viện mới. Đây là phép thử đặc biệt quan trọng khi thư viện được phân phối tới những consumer không được biên dịch lại đồng thời.

Một quy trình tối thiểu:

1. Chọn artifact v1, artifact v2 và consumer đã được build với v1.
2. Giữ nguyên bytecode consumer, không tự động biên dịch lại.
3. Đảm bảo runtime chỉ nạp phiên bản v2 ở vị trí cần thay thế.
4. Chạy những code path dùng API cũ.
5. Kiểm tra lỗi như `NoSuchMethodError`, `NoClassDefFoundError`, `AbstractMethodError`, `IllegalAccessError`.
6. Ghi nhận JDK, classpath/module path, dependency graph, log và kết quả.

Ví dụ về hai chiều thử nghiệm:

| Thử nghiệm | Consumer | Library khi chạy | Điều xác nhận |
|---|---|---|---|
| Baseline | Biên dịch với v1 | v1 | Consumer trước migration hoạt động |
| Binary upgrade | Giữ bytecode biên dịch với v1 | v2 | Consumer cũ còn liên kết và vận hành đúng ở những case đã thử |
| Recompile | Biên dịch source cũ với v2 | v2 | Source compatibility |
| Migrated consumer | Source đã đổi sang API v2 | v2 | Đường migration mới |
| Rollback (nếu hỗ trợ) | Consumer sau nâng cấp | v1 | Khả năng tương thích ngược hướng cũ khi cần rollback; không nên mặc định có |

Kết quả chạy thành công một code path không bảo đảm tất cả các class đều được tải hoặc mọi nhánh đã được thực thi. Cần kết hợp static analysis, test có chủ đích và quan sát runtime.

## 13. Kiểm chứng hành vi bằng contract test

Một thư viện có thể giữ mọi chữ ký nhưng thay đổi cách thực hiện. **Contract test** biến những điều consumer được phép dựa vào thành ví dụ đầu vào/đầu ra và quy tắc có thể kiểm tra.

Với API tra cứu khách hàng:

~~~java
public interface CustomerLookup {
    Optional<Customer> findById(String customerId);
}
~~~

Một số điều kiện cần test:

- ID tồn tại: Optional chứa đúng khách hàng.
- ID không tồn tại: Optional.empty, không có ngoại lệ “không tìm thấy”.
- Input không hợp lệ: hành vi theo hợp đồng (ví dụ IllegalArgumentException).
- Lỗi backend: không được âm thầm trả Optional.empty nếu contract quy định phát sinh lỗi.
- Gọi nhiều lần và đồng thời: tuân theo thread-safety/caching đã cam kết.
- Kết quả trả về: giữ quy tắc immutability hoặc ownership nếu có.

Ví dụ JUnit mang tính minh họa:

~~~java
@Test
void missingCustomerProducesEmptyResult() {
    CustomerLookup lookup = fixtureWithNoCustomer();

    Optional<Customer> result = lookup.findById("C-MISSING");

    assertTrue(result.isEmpty());
}
~~~

Contract test có giá trị nhất khi phản ánh use case thực và được chạy cho cả provider mới lẫn consumer đại diện, thay vì chỉ kiểm tra implementation tự viết theo giả định của chính tác giả.

Có thể xây bộ contract test chung chạy đối với version cũ và mới để tìm khác biệt chủ ý hoặc ngoài ý muốn. Nếu API mới đã công bố thay đổi ngữ nghĩa, cần phân tách test dành cho hợp đồng cũ và test dành cho hợp đồng mới.

## 14. Java runtime baseline cần kiểm riêng với phiên bản thư viện

Ví dụ một thư viện phát hành `2.5.0` nhưng đổi yêu cầu tối thiểu từ Java 11 lên Java 17. Dù API method không đổi, ứng dụng sản xuất đang chạy trên Java 11 không thể dùng artifact mới nếu bytecode hoặc API yêu cầu Java 17.

Một số class-file major version thông dụng:

| Java release | Class-file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Có thể dùng `javap -verbose` để xem `major version` của class:

~~~bash
javap -verbose -classpath customer-api.jar \
  com.example.api.CustomerApi
~~~

Tuy nhiên, kiểm một class chỉ xác nhận class ấy được tạo cho định dạng bytecode nào. Các class khác trong cùng JAR, multi-release JAR và dependency bắc cầu có thể có yêu cầu khác. Kiểm tra runtime trên JDK tối thiểu vẫn cần thiết.

### 14.1. Compile target không chứng minh runtime

Trong Gradle Kotlin DSL, có thể cấu hình:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

Trong ví dụ, compiler JDK 21 được yêu cầu biên dịch source theo luật ngôn ngữ, bytecode và API Java SE 17. Điều này không ép mọi dependency runtime tương thích Java 17, cũng không tự động chạy test trên JDK 17.

Muốn tuyên bố “thư viện chạy trên Java 17”, cần test với runtime Java 17 theo cấu hình đã xác định. Nếu hỗ trợ nhiều Java feature release, cân nhắc matrix CI với JDK tối thiểu và một số bản được hỗ trợ khác.

### 14.2. Tuyên bố hỗ trợ JDK phải có điều kiện

“Supports Java 17 and 21” cần xác định JDK distribution, OS/architecture, loại test và những module được kiểm tra. LTS hoặc nhãn cập nhật của vendor không thay thế bằng chứng runtime. Native dependencies, truststore, timezone, security provider, module access hoặc công cụ build có thể khác nhau dù số Java feature giống nhau.

## 15. Dependency graph là một phần của kết luận tương thích

Library version không tồn tại độc lập. Một artifact có thể kéo theo các dependency mới, thay đổi phiên bản transitive hoặc để lộ type bên ngoài trong API.

Ví dụ:

~~~kotlin
dependencies {
    implementation("com.example:customer-api:2.5.0")
}
~~~

Build tool sẽ giải quyết một dependency graph dựa trên các constraint, repository, BOM/platform và quy tắc conflict resolution. Ứng dụng khác trong cùng build có thể yêu cầu các version khác nhau của một dependency chung.

Các câu hỏi cần ghi nhận:

- Phiên bản thực sự được resolve là gì, có trùng với version mong muốn không?
- Dependency bắc cầu nào được nâng lên hoặc thay mới?
- Có xung đột class, method hay logging/HTTP/JSON runtime không?
- Có dependency nào yêu cầu JDK cao hơn baseline của ứng dụng không?
- Có library nào rò rỉ dependency implementation trong chữ ký API công khai không?
- BOM hoặc constraint có khiến việc nâng một artifact kéo theo nhiều artifact khác không?

Với Gradle có thể dùng các báo cáo dependency và dependency insight theo module:

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency customer-api
~~~

Các lệnh mang tính ví dụ; tên project/module và configuration thay đổi theo build thực tế. Một bản report dependency graph giúp giải thích môi trường đã kiểm tra, nhưng không chứng minh behavioral compatibility.

Nếu cần khả năng tái lập, nên quản lý resolved versions, dependency locking hoặc xác minh artifact theo chính sách của tổ chức. Tránh dựa vào version range không kiểm soát hoặc artifact mutable trong báo cáo tương thích.

## 16. Ma trận thử nghiệm cần phản ánh hướng nâng cấp

Không phải mọi hướng kết hợp consumer/provider đều được hỗ trợ. Cần ghi rõ hướng migration:

| Consumer / Provider | Provider cũ v1 | Provider mới v2 |
|---|---|---|
| Consumer cũ, bytecode cũ | Baseline bắt buộc hoạt động | Trọng tâm kiểm chứng binary compatibility |
| Consumer cũ, biên dịch lại | Kiểm tra source baseline khi cần | Trọng tâm kiểm chứng source compatibility |
| Consumer đã chuyển sang API mới | Có thể không được hỗ trợ | Kiểm chứng API và hành vi mới |
| Consumer chạy runtime cũ | Kiểm tra trong phạm vi hỗ trợ | Xác nhận runtime baseline có đáp ứng v2 không |

Tương thích **nâng cấp** (old consumer → new provider) không tự động kéo theo tương thích **rollback** (new consumer → old provider). Consumer mới gọi API chỉ tồn tại ở v2 sẽ không thể dùng provider v1 nếu không có phương án dự phòng.

Ngoài ra, hệ thống phân tán có thể triển khai không đồng thời. Khi producer v2 và consumer v1 cùng tồn tại, phải kiểm tra schema, event, header và protocol tương ứng. Một artifact Java “binary compatible” không đủ để chứng minh giao thức mạng hay database schema phù hợp.

## 17. Đánh giá độ mạnh của bằng chứng

Không phải bằng chứng nào cũng có cùng giá trị với mọi rủi ro:

| Bằng chứng | Mức độ khẳng định hợp lý | Điểm chưa đủ |
|---|---|---|
| Chỉ thấy version tăng PATCH | Ý định phát hành ít thay đổi | Không có kiểm tra consumer |
| Release notes nói “non-breaking” | Nhà cung cấp tuyên bố giữ tương thích | Có thể thiếu use case nội bộ |
| API diff sạch | Không phát hiện các loại API break mà công cụ kiểm tra | Chưa xác minh behavior/runtime |
| Consumer compile pass | Source consumer đã kiểm hợp lệ | Chưa chứng minh binary cũ hoặc runtime |
| Consumer bytecode cũ chạy test pass | Một số đường tương thích binary/runtime đã được thực thi | Chưa bao phủ mọi class/code path |
| Contract test pass | Hành vi được mô tả trong test còn đúng | Chưa chứng minh đặc tả test đầy đủ |
| Canary trên môi trường đại diện pass | Một tập luồng hoạt động khi triển khai | Chưa phản ánh mọi traffic, tải và sự kiện hiếm |
| Production rollout theo dõi ổn định | Bằng chứng vận hành trên traffic thực | Vẫn phải theo dõi thay đổi môi trường về sau |

Kết luận nên dựa trên **tập bằng chứng bù trừ nhau**. API diff kết hợp compile test, binary test, contract test và staging/canary mạnh hơn việc chỉ đọc release notes.

Phát hiện FAIL có giá trị đặc biệt: nó cho biết một giả định tương thích đã sai trong phạm vi phép thử. Không nên loại một lỗi khỏi báo cáo chỉ vì version trông có vẻ “an toàn”.

## 18. Thiết kế hồ sơ bằng chứng cho từng quyết định phát hành

Một quyết định go/no-go nên có hồ sơ ngắn, có thể truy vết đến artifact và test. Ví dụ:

~~~yaml
migration:
  component: customer-api
  fromVersion: "2.4.1"
  toVersion: "2.5.0"
  intendedConsumers:
    - consumer-a
    - consumer-b
  javaBaseline: "17"
  runtimeMatrix:
    - jdk: "17"
      os: "linux-x64"
    - jdk: "21"
      os: "linux-x64"
  verification:
    apiDiff: PASS
    sourceCompile: PASS
    oldBinaryRun: PASS
    contractTests: PASS
    integrationTests: PASS
  limitations:
    - external-consumers-not-enumerated
    - windows-not-tested
  decision: CONDITIONAL_GO
  rationale: "Supported internal consumers passed selected checks"
~~~

Đây là dữ liệu minh họa, không phải kết quả một lần kiểm thử thực tế. Trong vận hành, hồ sơ phải kèm link tới report và log, commit, checksum của JAR/container, dependency graph, thời gian kiểm tra, người chịu trách nhiệm và các ngoại lệ.

### 18.1. Tránh viết kết luận quá rộng

Không nên ghi:

> “2.5.0 is fully compatible with all previous versions.”

Nếu chỉ kiểm tra hai consumer nội bộ trên Linux/JDK 17, nên viết:

> “Các consumer nội bộ A và B đã vượt qua compile, binary và contract test khi chuyển 2.4.1 → 2.5.0 trên môi trường đã ghi nhận. Chưa kiểm tra consumer bên ngoài và Windows.”

Cách diễn đạt hẹp hơn không làm kết quả kém hữu ích; nó giúp người ra quyết định hiểu đúng mức rủi ro còn lại.

## 19. Quy trình quyết định nâng cấp theo bằng chứng

Một quy trình thực tế có thể triển khai theo các giai đoạn sau.

### Bước 1: Xác định phạm vi thay đổi

Ghi rõ artifact, phiên bản cũ/mới, JDK baseline, versioning policy và release notes. Đừng chỉ ghi “nâng thư viện lên bản mới nhất”.

### Bước 2: Đọc lời hứa của nhà cung cấp

Xem chính sách versioning, deprecation, breaking changes và hỗ trợ runtime. Nếu release có MAJOR bump, xem xét migration guide. Nếu PATCH, vẫn kiểm tra changelog và dependency change.

### Bước 3: Kiểm kê consumer và usage

Liệt kê source, bytecode triển khai, SPI implementor, reflection, code generator, configuration, data format và dependency quan trọng. Ưu tiên consumer có rủi ro cao hoặc lịch nâng cấp chậm.

### Bước 4: Chạy phân tích tĩnh

So sánh API, class-file version, module boundary và dependency graph. Ghi lại các cảnh báo và hạn chế của công cụ.

### Bước 5: Chạy source và binary test

Biên dịch lại consumer cũ với version mới; đồng thời giữ bytecode cũ và thử với provider mới. Hai thử nghiệm trả lời hai câu hỏi khác nhau.

### Bước 6: Chạy contract và integration test

Kiểm tra hành vi đã cam kết và các luồng lỗi quan trọng, đặc biệt null, exception, timeout, transaction, serialization và retry. Chạy trên JDK tối thiểu và môi trường quan trọng khác nếu thuộc phạm vi hỗ trợ.

### Bước 7: Thử triển khai có kiểm soát

Sử dụng staging hoặc canary với cấu hình gần production. Theo dõi lỗi JVM, HTTP, TLS, GC, memory, latency và chỉ số nghiệp vụ. Xác định rollback strategy trước khi triển khai rộng.

### Bước 8: Lưu bằng chứng và ra quyết định

Ghi kết quả PASS/FAIL, phạm vi chưa bao phủ, owner, rủi ro còn lại và điều kiện go/no-go. Nếu có FAIL, giải quyết trước hoặc chấp nhận ngoại lệ một cách minh bạch theo quy trình của tổ chức.

## 20. Một số hiểu lầm cần tránh

**“Đổi PATCH nên chắc chắn không breaking.”** PATCH thể hiện quy tắc phát hành dự kiến, không thay thế phép thử. Một bug fix có thể tác động consumer dựa vào hành vi chưa được cam kết.

**“Đổi MAJOR chắc chắn mọi consumer hỏng.”** Chỉ những consumer sử dụng phần bị thay đổi hoặc chịu ảnh hưởng gián tiếp mới có rủi ro tương ứng; vẫn phải phân tích.

**“Biên dịch thành công là tương thích.”** Compile pass không phát hiện đủ lỗi runtime, cấu hình hoặc hành vi.

**“API diff không báo lỗi nên an toàn.”** API diff chủ yếu xác nhận bề mặt mà công cụ kiểm tra; hành vi, dữ liệu và môi trường cần các test khác.

**“Đã chạy Java 21 trên máy dev nên production Java 17 chạy được.”** Cần kiểm tra class-file baseline, dependency, API nền tảng và runtime thực tế.

**“Nhà cung cấp nói hỗ trợ Java 17 tức mọi distribution, OS đều ổn.”** Tuyên bố hỗ trợ cần được đọc theo ma trận vendor và môi trường cụ thể.

**“Một kết quả test pass áp dụng cho mọi consumer.”** Mỗi consumer có usage, dependency graph, dữ liệu và deployment khác nhau.

**“Không thấy lỗi ở smoke test thì binary compatible.”** Smoke test có thể không thực thi method bị xóa hoặc nhánh plugin được tải động.

**“Version đã pin thì binary luôn giống nhau.”** Với artifact mutable, snapshot hoặc image tag được cập nhật, cùng một nhãn chưa chắc trỏ tới cùng bytes. Dùng checksum/digest và nguồn artifact đáng tin cậy khi cần tái lập.

## 21. Checklist trước khi công bố tính tương thích

- [ ] Đã xác định chính xác artifact, from/to version và chính sách versioning.
- [ ] Đã phân biệt metadata, tuyên bố và kết quả kiểm chứng thực tế.
- [ ] Đã xác định public API, các consumer và các use case quan trọng.
- [ ] Đã đánh giá source, binary, behavioral, runtime, dependency và build-time compatibility.
- [ ] Đã xem API diff và những thay đổi trong chữ ký, SPI, default method, overload.
- [ ] Đã biên dịch lại consumer cũ với provider mới trong môi trường đã xác định.
- [ ] Đã chạy consumer bytecode cũ với provider mới mà không biên dịch lại.
- [ ] Đã kiểm tra JDK baseline, class-file target, transitive dependency và module access.
- [ ] Đã chạy contract/integration test cho đường thành công, lỗi và trường hợp biên.
- [ ] Đã lưu JDK/vendor/build, OS, dependency graph, commit, artifact checksum và log.
- [ ] Đã ghi rõ consumer/platform chưa được kiểm tra, các ngoại lệ và rủi ro tồn đọng.
- [ ] Đã có quyết định go/no-go, owner, rollback plan và cách theo dõi sau triển khai.

## Kết luận

**Số phiên bản là nhãn và tín hiệu chính sách; bằng chứng tương thích là kết quả kiểm chứng có bối cảnh.** SemVer, MAJOR/MINOR/PATCH, LTS hoặc những lời công bố “backward compatible” giúp định hướng kế hoạch kiểm tra, nhưng không thể thay thế compile test, binary test, contract test, kiểm tra runtime và dependency trên các consumer thực tế.

Trong tiến hóa API của Java, nên mô tả tương thích theo từng chiều và từng cặp consumer–provider, ghi rõ từ version nào sang version nào, trên JDK/môi trường nào, với bộ kiểm thử và phạm vi nào. Cách tiếp cận dựa trên bằng chứng giúp nhóm nâng cấp có kiểm soát, phân biệt lỗi thật với giả định từ version number, và đưa ra quyết định phát hành hoặc migration có thể truy vết, kiểm chứng và lặp lại.
