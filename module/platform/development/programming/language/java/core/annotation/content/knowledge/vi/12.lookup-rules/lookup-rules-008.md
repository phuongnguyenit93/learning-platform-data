# Vì sao quét package, tìm lớp và tìm meta-annotation cần thuật toán riêng?

## 1. Ba bài toán không phải một

Khi xây framework, bộ đăng ký handler hoặc công cụ phân tích annotation trong Java, người học thường muốn viết: “Tìm mọi class trong package `com.example` có annotation `@ComponentLike` hoặc được đánh dấu gián tiếp qua một meta-annotation”. Câu mô tả nghe đơn giản nhưng thực chất gồm **ba bước độc lập**:

1. **Khám phá ứng viên (package/class discovery):** xác định các tên lớp hay đối tượng `Class<?>` có thể thuộc phạm vi cần xét.
2. **Chọn lớp phù hợp (class filtering):** với từng ứng viên đã biết, kiểm tra điều kiện như loại class, annotation trực tiếp, superclass, interface, tên package và quy tắc riêng.
3. **Giải quyết meta-annotation (meta-annotation resolution):** nếu một annotation được gắn trên **loại annotation khác**, duyệt các tầng annotation để suy ra vai trò mà ứng dụng muốn tìm.

Java Reflection cung cấp nhiều API để **kiểm tra một lớp/phương thức/annotation đã xác định**, chẳng hạn `getDeclaredAnnotations()`, `getAnnotation(...)` hay `getSuperclass()`. Nhưng Reflection **không có API Java SE duy nhất** đảm bảo tự liệt kê tất cả lớp của một package trong mọi kiểu đóng gói, class loader và module.

```text
Phạm vi nguồn cần tìm
  classpath / module path / thư mục class / JAR / registry đã đăng ký
                |
                v
[1] Khám phá các ứng viên Class<?>
    (phụ thuộc môi trường chạy và cơ chế đóng gói)
                |
                v
[2] Lọc lớp theo các điều kiện ứng dụng
    class? interface? annotation trực tiếp? superclass?
                |
                v
[3] Nếu cần, duyệt cây meta-annotation
    @RestEndpoint -> @HttpRole -> @Role("http")
                |
                v
Lập danh sách kết quả / đăng ký handler / sinh metadata
```

Không được nhầm “annotation có retention `RUNTIME`” với “JVM sẽ tự quét mọi package và đăng ký mọi lớp mang annotation”. Retention chỉ nói metadata còn có thể đọc **khi đã có đối tượng phản ánh đúng thành phần**. Hành vi tìm kiếm, khởi tạo và đăng ký phải do bên xử lý tổ chức.

## 2. Vì sao `Package` và `Class` không tự liệt kê tất cả lớp?

### `Class.forName(...)` yêu cầu biết tên

Ví dụ:

```java
Class<?> type = Class.forName("java.util.ArrayList");
```

Lệnh này lấy một loại khi **đã biết tên nhị phân**. Nó không thể tự suy ra “mọi lớp trong `java.util`”. Tương tự, `ClassLoader.loadClass(...)` nhận một tên lớp cần tải, chứ không trả danh sách tất cả tên lớp có thể tải.

Có thể dùng dạng:

```java
Class<?> type = Class.forName(
    "java.util.ArrayList",
    false,
    ClassLoader.getSystemClassLoader()
);
```

Đối số `false` yêu cầu không khởi tạo class chỉ vì lời gọi này; tuy nhiên, đây **vẫn là thao tác tải/xác định một class cụ thể**, không phải quét package. Việc liên kết, tải phụ thuộc và kiểm tra quyền có các tình huống lỗi riêng; không nên xem nó là cách liệt kê an toàn vô điều kiện.

### `Package` là thông tin về package, không phải danh mục tất cả class

Các API như `type.getPackage()`, `type.getPackageName()` hay `Package.getName()` trả về thông tin package của một class đã biết. `Package` **không có** phương thức chuẩn kiểu `getAllClasses()`.

Tương tự:

- `Class.getDeclaredClasses()` trả về **các kiểu thành viên được khai báo trực tiếp trong class đó**, không phải mọi class của cùng package.
- `getDeclaredMethods()` hay `getDeclaredFields()` liệt kê **thành viên của một class đã biết**, không mở rộng phạm vi sang các lớp khác.
- `ClassLoader.getDefinedPackages()` mô tả các package đã được định nghĩa bởi class loader, **không cung cấp danh sách mọi class** trong mỗi package và không thay thế bộ quét classpath.

**Kết luận:** trước khi gọi `getAnnotation(...)` trên hàng loạt lớp, chương trình phải có **một nguồn ứng viên**. Chẳng hạn hệ thống đã đăng ký sẵn danh sách `Class<?>`, build tool sinh một chỉ mục hoặc thư viện scanner khám phá classpath.

## 3. Vì sao quét package phụ thuộc nơi chứa class?

Một package Java là **không gian tên**. Nó không đồng nghĩa với một thư mục duy nhất trên máy:

| Nơi chứa class | Một cách khám phá khả dĩ | Điểm cần lưu ý |
| --- | --- | --- |
| Thư mục class đã biên dịch | Duyệt đường dẫn theo cấu trúc package và tên tệp `.class` | Không phải mọi mục đều là class được phép tải; cần xác định binary name |
| JAR thông thường | Liệt kê `JarEntry` trong JAR, lọc các `.class` | Package có thể trải trên nhiều JAR; cần chọn đúng container |
| Ứng dụng dùng nhiều class loader | Quét nguồn tương ứng từng loader được phép | Cùng binary name ở các loader khác nhau có thể là các `Class` khác nhau |
| Java Module System (JPMS) | Xác định module/layer phù hợp và cách mở/đọc nội dung module | Package name đơn thuần không đủ để truy cập hoặc duyệt mọi module |
| Executable/fat JAR, nested JAR hoặc cơ chế đóng gói đặc biệt | Cần scanner hoặc chỉ mục hiểu bố cục tương ứng | Giả định “mọi lớp là một file trên filesystem” có thể sai |
| Class được tạo/tải động | Registry hoặc cơ chế quan sát riêng | Một lần quét classpath không bảo đảm thấy mọi class có thể xuất hiện sau đó |

API `ClassLoader.getResources("com/example")` đôi khi giúp tìm các resource có tên giống đường dẫn package. Nhưng nó **không phải lời hứa Java SE** rằng mọi package sẽ có resource thư mục và mọi cách đóng gói đều cho phép liệt kê class qua đó. Một JAR có class entry nhưng không có directory entry tương ứng; loader tùy chỉnh có thể trình bày resource khác cách file/JAR thường.

Ngay cả khi liệt kê được mọi `.class` ở một container, còn phải giải quyết:

- Chuyển tên tệp thành **binary name** hợp lệ (bao gồm kiểu lồng nhau như `Outer$Inner`).
- Loại bỏ hoặc xử lý hợp lý `module-info.class`, `package-info.class` và các dạng entry đặc biệt.
- Không tải nhầm bản class trong multi-release JAR hoặc tài nguyên không tương thích với runtime.
- Tránh load các class không cần thiết và quản lý lỗi như `ClassNotFoundException`, `LinkageError` khi có phụ thuộc không đáp ứng.
- Xác định liệu chỉ quét **một package** hay cả **package con**; Java không coi package con là “thành viên” của package cha.
- Quy định phạm vi module, class loader, thư mục/JAR cho phép quét, tránh thực thi plugin không tin cậy một cách vô ý.

Đây là lý do nhiều hệ thống dùng thư viện scanner chuyên biệt hoặc **sinh index lúc build** thay vì tự viết một hàm Reflection ngắn giả vờ hỗ trợ mọi môi trường.

## 4. Có danh sách class rồi, vẫn phải lọc theo quy tắc nào?

Sau bước khám phá, mỗi ứng viên được biểu diễn bằng đối tượng `Class<?>`. Bạn có thể kiểm tra:

```java
boolean isInterface = type.isInterface();
boolean isAnnotationType = type.isAnnotation();
boolean isEnum = type.isEnum();

boolean directlyMarked =
        type.isAnnotationPresent(SomeMarker.class);
```

Nhưng câu hỏi “có được chọn?” phải nêu chính xác.

Ví dụ, nếu một ứng dụng muốn chọn **class cụ thể có annotation trực tiếp**, cần loại interface, annotation type, enum, abstract class (nếu không hỗ trợ) và chọn cách đọc **declared annotations** thay vì dùng một API có thể xét kế thừa.

Nếu muốn tìm **các lớp triển khai một interface**, quan hệ kiểu như `ApiHandler.class.isAssignableFrom(type)` là điều kiện khác với annotation. Nó cũng không tự đảm bảo class có thể khởi tạo, có constructor thích hợp hoặc nên được đăng ký.

### Trực tiếp và kế thừa không đồng nghĩa

Giả sử loại annotation `@Registered` có `@Inherited`, được gắn trên class cha. Khi đó:

- `Child.class.getAnnotation(Registered.class)` **có thể** trả annotation từ superclass trong điều kiện `@Inherited` phù hợp.
- `Child.class.getDeclaredAnnotation(Registered.class)` chỉ trả annotation **trực tiếp** trên `Child`.
- `@Inherited` không tự truyền metadata từ interface được implement hay từ method bị override.

Nếu hệ thống muốn quét interface hierarchy hoặc superclass theo quy tắc riêng, nó phải chọn chiến lược duyệt tương ứng. Không thể vừa nói “chỉ trực tiếp” vừa vô tình dùng API cho phép kế thừa mà không kiểm tra hậu quả.

### Kết quả phải có chính sách rõ ràng

Một scanner cần trả lời những câu hỏi thiết kế: chỉ lấy public class hay tất cả? có tính nested class không? có tính abstract class không? loại bỏ duplicate theo `Class<?>` hay theo binary name? annotation trên superclass được xét không? có lấy annotation trên interface không? có quét mọi module hay chỉ một module?

Đó là **quy tắc của ứng dụng**, không phải hành vi mặc định khi khai báo `@Target` hay `@Retention`.

## 5. Meta-annotation là gì và vì sao cần duyệt?

**Meta-annotation** là annotation được gắn trên **khai báo loại annotation khác**.

Ví dụ cấu trúc:

```java
@Role("http")
@interface HttpRole {}

@HttpRole
@interface RestEndpoint {}

@RestEndpoint
class TicketController {}
```

Ba đoạn trên chỉ minh họa quan hệ và **cần khai báo `Role`, chính sách `@Target`, `@Retention` thích hợp** để biên dịch đúng. Ví dụ đầy đủ ở mục 7.

Nếu kiểm tra:

```java
TicketController.class.getDeclaredAnnotation(Role.class)
```

kết quả là `null` vì class chỉ được gắn **`@RestEndpoint`**, không trực tiếp gắn `@Role`. Tương tự, `RestEndpoint.class.getDeclaredAnnotation(Role.class)` là `null`, vì `@Role` chỉ được gắn trực tiếp lên khai báo `HttpRole`.

Muốn suy ra TicketController có “vai trò HTTP” theo quy ước của framework, bạn phải đi theo chuỗi:

```text
TicketController
    └── @RestEndpoint
           └── trên khai báo RestEndpoint có @HttpRole
                  └── trên khai báo HttpRole có @Role("http")
```

Java Reflection có thể giúp bạn đọc từng mắt xích qua `getDeclaredAnnotations()` và `annotation.annotationType()`. Nhưng nó **không tự tạo thuật toán truy tìm bắc cầu mọi meta-annotation** từ một class đến annotation ở nhiều tầng.

### Các giới hạn cần tự quyết định

- **Độ sâu:** chỉ tìm meta-annotation trực tiếp hay duyệt nhiều tầng?
- **Chu trình:** annotation type có thể tham chiếu qua chuỗi meta-annotation gây lặp; dùng tập `visited` để tránh quay vòng.
- **Độ ưu tiên:** nếu có nhiều nhánh cung cấp cùng một marker với giá trị khác nhau, chọn nhánh nào? Không nên dựa vào thứ tự không được đảm bảo của `getDeclaredAnnotations()`.
- **Annotation chuẩn:** có muốn duyệt `@Target`, `@Retention`, `@Documented`...? Thường cần bỏ qua nếu không liên quan nghiệp vụ.
- **Retention:** muốn thấy từng tầng bằng Reflection runtime thì các annotation trên mắt xích ấy phải có retention phù hợp, thường là `RUNTIME`.
- **Annotation lặp:** loại `@Repeatable` có container; nếu nghiệp vụ hỗ trợ repeated annotations, cần xác định cách đọc `getAnnotationsByType(...)` hoặc cách giải container.
- **Kế thừa/interface:** duyệt meta-annotation khác với duyệt superclass hoặc interface. `@Inherited` không đồng nghĩa với việc meta-annotation tự lan bắc cầu.
- **An toàn và hiệu năng:** cache kết quả hợp lệ khi có chính sách vô hiệu hóa phù hợp; tránh quét/tải và phân tích lại cùng class quá nhiều lần.

Với yêu cầu trả **một vai trò duy nhất**, thuật toán cần tiêu chí chống xung đột. Với yêu cầu gom **mọi vai trò**, kết quả nên là tập/collection đã chuẩn hóa và có thứ tự trình bày xác định.

## 6. Thiết kế thuật toán ở mức khái niệm

Có thể tách thành ba hàm, mỗi hàm có trách nhiệm rõ:

```text
discoverCandidates(scope):
    names = enumerateClassesFromConfiguredSources(scope)
    return loadOrResolveCandidateClasses(names)

matchesDirectRules(candidate):
    check class kind, package restrictions, direct annotations,
          interface/superclass relationships as required

resolveMetaAnnotation(annotationType, visited):
    if annotationType already in visited: stop this branch
    mark visited
    if annotationType directly has requested marker: return it
    for each relevant meta-annotation on annotationType:
        result = resolveMetaAnnotation(meta.annotationType(), visited)
        if found: return result
    return not found
```

Đây là **giả mã thuật toán**, không phải Java chạy độc lập. Đặc biệt, `enumerateClassesFromConfiguredSources` phải có cài đặt tương thích với container/class loader/module của ứng dụng; không có một phép Reflection Java SE phổ quát thay thế nó.

Khi áp dụng trong thực tế, nên thêm bước quyết định **khi nào và ở đâu** chạy: lúc build để sinh index, lúc khởi động ứng dụng để tạo registry, hay trong quá trình xử lý request. Thường nên tránh quét toàn bộ classpath ở mỗi request vì chi phí I/O, class loading và Reflection.

## 7. Ví dụ Java 17+ chạy độc lập: tìm meta-annotation khi ứng viên đã được cung cấp

Ví dụ này **không giả vờ quét package**. Để giữ chương trình Java SE ngắn, chạy ổn định ở mọi máy có JDK 17+, ta **đăng ký sẵn danh sách class ứng viên** rồi minh họa riêng hai bước tiếp theo: lọc và duyệt meta-annotation.

Tạo file **`MetaAnnotationLookupDemo.java`**:

```java
import java.lang.annotation.Annotation;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.HashSet;
import java.util.Set;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface Role {
    String value();
}

@Role("http")
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface HttpRole {}

@HttpRole
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RestEndpoint {}

@RestEndpoint
class TicketController {}

@RestEndpoint
interface TicketContract {}

class PlainHelper {}

public class MetaAnnotationLookupDemo {
    private static Role findRole(
            Class<? extends Annotation> annotationType,
            Set<Class<? extends Annotation>> visited) {

        if (!visited.add(annotationType)) {
            return null;
        }

        Role direct = annotationType.getDeclaredAnnotation(Role.class);
        if (direct != null) {
            return direct;
        }

        for (Annotation meta : annotationType.getDeclaredAnnotations()) {
            Class<? extends Annotation> next = meta.annotationType();

            if (next.getName().startsWith("java.lang.annotation.")) {
                continue;
            }

            Role found = findRole(next, visited);
            if (found != null) {
                return found;
            }
        }
        return null;
    }

    private static String roleOf(Class<?> candidate) {
        for (Annotation direct : candidate.getDeclaredAnnotations()) {
            Role found = findRole(
                    direct.annotationType(),
                    new HashSet<>());
            if (found != null) {
                return found.value();
            }
        }
        return "none";
    }

    public static void main(String[] args) {
        // Đây là các ứng viên đã biết, KHÔNG phải kết quả quét package.
        Class<?>[] candidates = {
            TicketController.class,
            TicketContract.class,
            PlainHelper.class
        };

        for (Class<?> candidate : candidates) {
            System.out.println(candidate.getSimpleName()
                    + " -> " + roleOf(candidate));
        }

        System.out.println("Role directly on controller: "
                + (TicketController.class
                    .getDeclaredAnnotation(Role.class) != null));
        System.out.println("Role directly on RestEndpoint: "
                + (RestEndpoint.class
                    .getDeclaredAnnotation(Role.class) != null));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MetaAnnotationLookupDemo.java
java MetaAnnotationLookupDemo
```

Kết quả **stdout chính xác**:

```text
TicketController -> http
TicketContract -> http
PlainHelper -> none
Role directly on controller: false
Role directly on RestEndpoint: false
```

### Giải thích luồng tìm kiếm

**`TicketController`:** đối tượng `Class` mang trực tiếp `@RestEndpoint`. `roleOf(...)` duyệt danh sách annotation trực tiếp của class, bắt đầu với loại `RestEndpoint`. Tại đó chưa có `@Role` trực tiếp, nhưng `getDeclaredAnnotations()` lấy ra `@HttpRole`. Đến loại `HttpRole`, lời gọi `getDeclaredAnnotation(Role.class)` tìm thấy `@Role("http")` và trả về giá trị `"http"`.

**`TicketContract`:** interface cũng mang trực tiếp `@RestEndpoint`, nên thuật toán ứng dụng tìm được `"http"`. Đây là **quét trực tiếp một interface đã có trong danh sách ứng viên**, không phải bằng chứng rằng annotation được Java `@Inherited` truyền từ interface sang class thực thi.

**`PlainHelper`:** không có annotation trực tiếp liên quan, nên hàm trả `"none"`.

**Hai dòng cuối:** bản thân `TicketController` và loại `RestEndpoint` đều **không được gắn trực tiếp `@Role`**, nên `getDeclaredAnnotation(Role.class)` trên chúng trả `null`. Kết quả `"http"` xuất hiện vì chương trình **chủ động duyệt nhiều tầng**.

### Vì sao có tập `visited`?

`visited.add(annotationType)` trả về `false` nếu loại annotation đã được thăm. Vì thế, nếu trong một đồ thị meta-annotation có chu trình, việc đệ quy sẽ dừng ở nhánh quay lại nút cũ thay vì lặp vô hạn.

Mã ví dụ tạo một tập mới cho mỗi annotation trực tiếp của một candidate, bảo đảm một nhánh không bị ảnh hưởng bởi nhánh của candidate khác. Với ứng dụng lớn, có thể thiết kế cache theo annotation type sau khi làm rõ chiến lược ưu tiên và xử lý xung đột.

### Giới hạn có chủ ý của chương trình

- Không khám phá class từ package/JAR/module: **mảng `candidates` là đầu vào sẵn có**.
- Chọn giá trị đầu tiên tìm thấy. Nếu một annotation type có nhiều nhánh metadata trái nhau, thứ tự duyệt không phải chính sách phù hợp cho sản phẩm thực tế; phải định nghĩa rõ ưu tiên hoặc báo xung đột.
- Bỏ qua các meta-annotation trong package `java.lang.annotation` để giới hạn phạm vi. Một consumer chuyên về các meta-annotation chuẩn có thể cần quy tắc khác.
- Không tự duyệt superclass hoặc interface của một class ứng viên, không mở container của repeated annotation, không xử lý mọi tình huống bảo mật/class loading.
- Chỉ có các annotation được giữ đến runtime mới được quan sát bằng Reflection theo cách này.

Đây là ví dụ minh họa **đúng ranh giới trách nhiệm**: Java Reflection đọc metadata trên class đã biết; thuật toán của chúng ta quyết định tìm sâu bao nhiêu và kết luận như thế nào.

## 8. Compile-time indexing và runtime scanning khác nhau ở đâu?

Một hệ thống có thể chọn khám phá class ở các thời điểm khác nhau:

| Cách tiếp cận | Làm gì? | Ưu điểm | Hạn chế cần cân nhắc |
| --- | --- | --- | --- |
| Đăng ký tường minh | Người lập trình cung cấp các `Class<?>` hoặc tên lớp | Dễ hiểu, ít phụ thuộc đóng gói | Phải duy trì danh sách khi thêm/bớt class |
| Annotation processing khi build | Annotation processor xử lý các phần tử source được compiler cung cấp, sinh registry hoặc metadata | Đưa một phần công việc sang compile-time | Không mặc nhiên khám phá toàn bộ dependency/JAR/module nếu pipeline không cung cấp |
| Sinh chỉ mục khi đóng gói | Plugin/build tool quét các class artifact đã biết và ghi index | Có thể rút ngắn khám phá lúc khởi động | Index có thể lỗi thời khi artifact thay đổi |
| Runtime classpath scanning | Duyệt container phù hợp, xác định tên/lớp, rồi đọc metadata | Linh hoạt với classpath được cấu hình | Phụ thuộc môi trường và tốn I/O, class loading; cần xử lý các trường hợp đặc biệt |
| Registry do framework xây dựng | Framework kiểm soát đăng ký và lookup theo hệ sinh thái của nó | Có thể hỗ trợ component model, cache, điều kiện riêng | Không phải hành vi tự động của Java Reflection thuần |

Một **annotation processor** làm việc trên các phần tử mà compiler đưa vào quá trình biên dịch; nó không trở thành một “máy quét package runtime” chỉ vì có API duyệt annotation.

Ngược lại, scanner runtime có thể gặp metadata có retention `RUNTIME` nếu dùng Reflection, hoặc có thể phân tích `.class` bằng thư viện bytecode để đọc những annotation có retention `CLASS`. Cần xác định **công cụ đọc nào** trước khi chọn retention.

Framework như Spring thường cung cấp hệ thống quét/đăng ký và xử lý metadata riêng. Khi một Spring stereotype gián tiếp được phát hiện, đó là **khả năng của thuật toán/framework**, không phải lời hứa rằng `Class.getAnnotation(...)` của Java luôn duyệt tất cả tầng meta-annotation.

## 9. Cách kiểm chứng lỗi khi “scanner không tìm thấy class”

Hãy chẩn đoán theo **ba tầng**, thay vì sửa annotation ngay:

**Tầng A — Khám phá ứng viên:**

- Class có nằm trong artifact mà scanner được cấu hình quét không?
- Package được cấu hình có đúng và có bao gồm package con cần thiết không?
- Có class loader/module khác đang chứa class không?
- Class đã bị loại vì không thể tải, không có quyền truy cập hoặc do bộ lọc tên/module chưa đúng?

**Tầng B — Lọc ứng viên:**

- Đích `@Target` có cho phép gắn annotation tại vị trí đang xét không?
- Metadata nằm trên class hay method/field? `Class.getAnnotation` không đọc annotation trên mọi method của class.
- Dùng `getDeclaredAnnotation` hay `getAnnotation` có xét `@Inherited`? Consumer có xét interface không?
- Class có phải abstract/interface/enum và bị loại bởi quy tắc riêng của registry không?

**Tầng C — Giải meta-annotation:**

- Annotation tìm kiếm có được gắn **trực tiếp**, hay nằm trên annotation khác qua một hoặc nhiều tầng?
- Từng mắt xích có retention cần thiết cho công cụ đọc không?
- Thuật toán có dừng trước độ sâu cần tìm, bỏ qua một nhánh, hoặc gặp chu trình chưa được xử lý không?
- Nếu nhiều annotation cùng loại hoặc nhiều nhánh có giá trị khác nhau, chính sách ưu tiên là gì?

Cách chia tầng giúp tránh lỗi phổ biến: cố “sửa `@Retention(RUNTIME)`” trong khi scanner **chưa bao giờ tìm đến class chứa annotation**, hoặc cố quét thêm JAR trong khi class đã được tìm thấy nhưng điều kiện lọc hoặc meta-resolution không đúng.

## 10. Những hiểu nhầm cần tránh

1. **“`Class.getPackage()` trả mọi class trong package.”** Sai: nó mô tả package của một class đã biết.
2. **“`ClassLoader.getResources(packagePath)` chắc chắn tìm đủ mọi class.”** Sai: sự hiện diện và khả năng liệt kê directory resource phụ thuộc loader và cách đóng gói.
3. **“`@Retention(RUNTIME)` khiến JVM tự động đăng ký class được gắn annotation.”** Sai: metadata khả dụng không đồng nghĩa có discovery hay consumer.
4. **“`getAnnotation(Marker.class)` luôn thấy meta-annotation nhiều tầng.”** Sai: phải có thuật toán đi qua loại annotation và các meta-annotation; `@Inherited` cũng không thay thế thuật toán đó.
5. **“Package cha tự chứa các package con.”** Sai: package `a` và `a.b` là các namespace khác nhau trong Java; recursion là lựa chọn của scanner.
6. **“Gắn annotation trên interface thì class implement đương nhiên có annotation đó.”** Sai với `@Inherited` của Java; framework có thể thêm lookup riêng.
7. **“Tìm được class nghĩa là có thể khởi tạo class ấy.”** Sai: class có thể là abstract/interface hoặc có constructor, visibility và yêu cầu khởi tạo khác.
8. **“Một nhánh meta-annotation trả marker là đủ trong mọi hệ thống.”** Chưa chắc: cần xử lý mâu thuẫn, đa annotation, repeatable annotations và quy tắc ưu tiên.
9. **“Duyệt `getDeclaredAnnotations()` nhiều lần không có chi phí đáng kể.”** Ở hệ thống lớn, lặp lại thường xuyên có thể tốn tài nguyên; hãy xem xét cache hoặc index.
10. **“Tất cả class có cùng tên đều là cùng một loại.”** Không nhất thiết: class loader và module có thể ảnh hưởng định danh và khả năng truy cập class.

## 11. Bài tập tự kiểm tra

**Bài 1.** Vì sao `Class.forName("com.example.Order")` không giải được yêu cầu “tìm mọi class trong `com.example`”?

**Đáp án:** `Class.forName` nhận tên một class đã biết. Muốn liệt kê ứng viên cần cơ chế duyệt các nguồn chứa class, index hoặc registry riêng.

**Bài 2.** `@Role` gắn trên `@HttpRole`, `@HttpRole` gắn trên `@RestEndpoint`, còn class `TicketController` chỉ có `@RestEndpoint`. `TicketController.class.getDeclaredAnnotation(Role.class)` tìm thấy không?

**Đáp án:** Không. `Role` không được gắn trực tiếp lên class. Consumer phải đi từ `RestEndpoint` đến `HttpRole` rồi đến `Role`.

**Bài 3.** Trong chương trình mẫu, vì sao `TicketContract` (interface) được in `http` dù `@Inherited` không truyền từ interface sang class?

**Đáp án:** `TicketContract` là **ứng viên trực tiếp** và được gắn `@RestEndpoint` trực tiếp. Thuật toán duyệt meta-annotation trên annotation ấy; không có chuyện kế thừa interface sang class.

**Bài 4.** Một scanner tìm được class nhưng không tìm thấy marker nằm sâu hai tầng. Nên kiểm tra ở tầng nào?

**Đáp án:** Tầng **giải meta-annotation**: depth, retention, filtering, visited/cycle và cách nhận diện marker. Discovery đã thành công.

**Bài 5.** Vì sao cần `visited` khi dùng đệ quy trên meta-annotation?

**Đáp án:** Để tránh duyệt lại một annotation type đã thăm, đặc biệt nếu đồ thị meta-annotation có vòng lặp.

**Bài 6.** Nếu cùng một annotation type có hai chuỗi meta-annotation dẫn đến hai giá trị vai trò mâu thuẫn, code mẫu đã xác định rõ chính sách giải quyết chưa?

**Đáp án:** Chưa. Nó chọn giá trị đầu tiên tìm thấy; ứng dụng thực tế cần định nghĩa ưu tiên ổn định hoặc phát hiện/báo xung đột.

**Bài 7.** Một framework dùng thư viện đọc trực tiếp `.class` phát hiện được annotation retention `CLASS`, còn `getAnnotation` runtime không thấy. Có mâu thuẫn không?

**Đáp án:** Không. Bytecode scanning và Reflection là hai cơ chế đọc với khả năng khác nhau.

**Bài 8.** Với một hệ thống lớn cần tốc độ khởi động nhanh và biết hết handler ở build-time, cách nào đáng cân nhắc?

**Đáp án:** Annotation processing hoặc sinh index/registry trong quá trình build, nếu quy trình build có đủ thông tin ứng viên. Cần quản lý tính đồng bộ của index khi ứng dụng thay đổi.

**Kết luận:** Quét package là **khám phá nguồn class**, tìm lớp là **lọc ứng viên**, còn tìm meta-annotation là **duyệt một đồ thị metadata**. Reflection hỗ trợ thao tác trên những `Class` và annotation đã biết, chứ không tự đảm nhiệm cả ba bài toán. Một framework đáng tin cậy phải định nghĩa rõ phạm vi khám phá, quy tắc lọc, cách duyệt meta-annotation và hành vi khi không có kết quả hoặc có nhiều kết quả.
