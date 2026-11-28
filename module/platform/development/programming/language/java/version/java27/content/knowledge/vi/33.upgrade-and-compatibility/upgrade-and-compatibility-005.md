# Thay API lỗi thời hoặc được đánh dấu loại bỏ bằng API còn được hỗ trợ

Khi nâng cấp một ứng dụng lên **Java 27**, việc biên dịch thành công không đồng nghĩa mọi API mà chương trình sử dụng đều phù hợp để tiếp tục duy trì. Một API có thể còn tồn tại nhưng đã được đánh dấu `@Deprecated`; một API khác đã được đánh dấu **forRemoval**; còn API đã bị xóa sẽ không thể được tham chiếu bằng mã nguồn Java 27 như trước.

Bài thuộc chương **Nâng cấp và tương thích Java 27**, trong module **Java 27 và các kiến thức liên quan**. Mục tiêu là xây dựng quy trình **nhận diện → phân loại → thay thế → kiểm chứng** những API cần di chuyển, với lựa chọn **đang được Java SE 27 hỗ trợ**. Những đoạn mã cũ chỉ xuất hiện ở chỗ minh họa **điều cần bỏ**, không phải khuyến nghị sử dụng mới. Không giả định một API bị loại bỏ luôn có bản thay thế tương đương một-một.

Đặc biệt cần chú ý các mốc thực tế:

- **JDK 24:** Security Manager bị vô hiệu hóa vĩnh viễn theo JEP 486. Nó vẫn xuất hiện dưới dạng API bị đánh dấu loại bỏ ở Java 27, nhưng không còn đóng vai trò sandbox Java trong tiến trình.
- **JDK 26:** `Thread.stop()` và API Applet đã bị **loại bỏ**, không phải chỉ còn cảnh báo deprecated. Java 27 không thể dùng các API này như trước.
- **JDK 27:** một số API trong `java.lang.reflect.Modifier` và `com.sun.source.util.SourcePositions`/`DocSourcePositions` mới được đánh dấu deprecated; hướng di chuyển chính thức là `AccessFlag` và các overload mới không cần `CompilationUnitTree`.
- Những API như `Class.newInstance()`, constructor `URL`, constructor `Locale` và `Object.finalize()` vẫn cần được đánh giá theo tình trạng cụ thể của từng API.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `@Deprecated`, `@Deprecated(forRemoval = true)` và API đã bị xóa.
2. Dùng tài liệu **Deprecated API** và **Removed APIs** của chính Java SE 27 để xác minh trạng thái thay vì dựa trên danh sách lỗi thời.
3. Phát hiện việc sử dụng API deprecated bằng `javac -Xlint`, `jdeprscan` và dependency nội bộ bằng `jdeps`.
4. Chọn đúng thời điểm thay API: ưu tiên lỗi compile/runtime, API bị đánh dấu loại bỏ, sau đó API deprecated thông thường có rủi ro.
5. Thay `Class.newInstance()` bằng phản chiếu qua `Constructor.newInstance()` với xử lý ngoại lệ phù hợp.
6. Thay lối dừng thread cưỡng bức đã bị xóa bằng **cooperative cancellation** và quản lý vòng đời tác vụ.
7. Thay cơ chế `finalize()` bằng ownership rõ ràng, `AutoCloseable` và `try`-with-resources.
8. Không tìm “sandbox SecurityManager mới” trong Java; thay bằng biện pháp kiểm soát ở kiến trúc và hệ điều hành.
9. Dùng `VarHandle` hoặc FFM khi di chuyển những thao tác phù hợp từ `sun.misc.Unsafe`, không giả định tương đương tuyệt đối.
10. Thay constructor `URL` bằng `URI` và `toURL()` khi thật sự cần `URL`.
11. Thay cách mã hóa form và tạo `Locale`/ngày giờ bằng API rõ charset/locale/time zone.
12. Dùng `ProcessBuilder` với từng phần tử tham số thay cho `Runtime.exec(String)`.
13. Nắm những thay đổi cụ thể của JDK 27 ở `Modifier`/`AccessFlag` và compiler-tree APIs.
14. Đánh giá tính tương thích nguồn, bytecode, hành vi, serialization, thư viện bên thứ ba và deployment.
15. Lập kế hoạch migration có test, quan sát runtime, rollback và không che cảnh báo vô hạn.

## 2. Ba trạng thái API bắt buộc phân biệt

### 2.1. Deprecated nhưng vẫn có thể sử dụng

Một thành viên được gắn `@Deprecated` thường vẫn có trong API và có thể biên dịch, nhưng tác giả API khuyến nghị ngừng sử dụng. Lý do có thể là thiết kế gây hiểu nhầm, API mới an toàn hơn hoặc hành vi không còn phù hợp.

~~~java
@Deprecated(since = "27")
public void oldOperation() {
    // Chỉ minh họa cách một thư viện đánh dấu deprecation.
}
~~~

Annotation này tự nó **không xóa phương thức**, và không bảo đảm phương thức sẽ biến mất ở phiên bản tiếp theo. `since` là thời điểm bắt đầu đánh dấu, không phải ngày dự kiến xóa.

### 2.2. Deprecated for removal

~~~java
@Deprecated(since = "27", forRemoval = true)
public void obsoleteOperation() {
    // Ví dụ annotation, không phải API JDK cụ thể.
}
~~~

`forRemoval = true` thể hiện ý định loại bỏ trong tương lai, cần ưu tiên thay thế. Nhưng nó **không phải lịch xóa chắc chắn trong một release cụ thể**. Kiểm tra release notes/JEP/Deprecated List để biết trạng thái thực tại Java 27.

### 2.3. API đã bị loại bỏ

Nếu type hoặc method thực sự bị xóa, code tham chiếu trực tiếp không còn compile dưới Java 27. Binary cũ có thể xuất hiện các lỗi liên kết như `NoSuchMethodError` hoặc `NoClassDefFoundError` khi runtime đi tới đoạn code liên quan.

Ví dụ, `Thread.stop()` đã bị loại bỏ trong JDK 26; không viết mã Java 27 mới gọi nó rồi mong nhận một warning bình thường. Với Applet (`java.applet`, `javax.swing.JApplet`), không có thay thế tương đương một-một trong Java SE 27.

### 2.4. Bảng quyết định

| Trạng thái | Điều có thể xảy ra ở Java 27 | Hành động nên làm |
|---|---|---|
| Deprecated thông thường | Vẫn compile, có cảnh báo ở nơi dùng | Đánh giá lý do deprecated, lựa chọn thay thế và semantic differences |
| Deprecated for removal | Vẫn có thể compile nhưng cảnh báo nghiêm trọng hơn | Ưu tiên trong backlog, đánh giá dependency/transitive impact |
| Đã bị xóa | Source không compile; binary có thể lỗi liên kết khi chạy | Bắt buộc thiết kế đường thay hoặc loại bỏ feature |
| API nội bộ `sun.*` / `jdk.internal.*` | Không có hợp đồng public; có thể gặp module encapsulation hoặc cảnh báo | Dùng Java SE/JDK API xuất công khai, đánh giá migration |
| API cũ nhưng **không deprecated** | Vẫn được hỗ trợ | Không thay chỉ vì tên cũ; quyết định dựa vào yêu cầu thực |
| API deprecated **không có direct replacement** | Không thể đổi bằng find-and-replace | Cần thay đổi thiết kế/hợp đồng/hạ tầng |

**Không xem “deprecated” đồng nghĩa “đã bị loại bỏ”.** Cũng không xem một API **không deprecated** như `java.io.File`, `synchronized` hay `java.util.Date` (một số constructor/method mới là deprecated) là “không còn được hỗ trợ”.

## 3. Nguồn thông tin đáng tin cho từng API

Thứ tự xác minh nên là:

1. **Java SE 27 Deprecated API List:** danh sách đang deprecated, bao gồm nhóm terminally deprecated.
2. **Oracle JDK 27 Migration Guide — Removed APIs:** type/method bị xóa ở các bản trước và những deprecation đáng lưu ý của 27.
3. **Javadoc chính xác của class/method:** mô tả vì sao deprecated và API được đề xuất thay.
4. **JDK 27 Release Notes và JEP liên quan:** nếu thay đổi có ảnh hưởng tương thích runtime/deployment.
5. **Tài liệu driver/framework/vendor:** khi deprecated thuộc thư viện bên thứ ba, không phải Java SE.

Ví dụ, `Thread.getId()` deprecated nhưng `Thread.threadId()` được khuyến nghị. Trong khi `SecurityManager` có ghi rõ **không có replacement**. Nếu cố tìm một method mới có tên tương tự cho Security Manager, rất dễ đưa ra hướng dẫn sai.

## 4. Phát hiện API deprecated trong source và bytecode

### 4.1. Cảnh báo từ javac

Khi biên dịch bằng **JDK 27**, có thể bật cảnh báo:

~~~bash
javac --release 27 \
      -Xlint:deprecation,removal \
      -d out \
      src/com/example/App.java
~~~

Giả định source path hợp lệ, và có classpath/module path nếu code có dependencies. `deprecation` nêu các API deprecated, còn `removal` tập trung cảnh báo ở API bị đánh dấu loại bỏ.

Có thể dùng `-Werror` khi một tập module đã sạch warning:

~~~bash
javac --release 27 \
      -Xlint:deprecation,removal \
      -Werror \
      -d out \
      src/com/example/App.java
~~~

`-Werror` làm lỗi **khi có warning** nói chung, không chỉ một loại warning đã chọn; áp dụng có lộ trình, tránh khóa toàn bộ codebase khi còn warnings không liên quan.

### 4.2. Dùng jdeprscan cho JAR/class files đã compile

~~~bash
# Quét deprecated APIs trong một artifact.
jdeprscan --release 27 \
           --class-path "lib/*" \
           app.jar

# Chỉ các API marked for removal.
jdeprscan --release 27 \
           --for-removal \
           --class-path "lib/*" \
           app.jar

# Liệt kê API hiện marked for removal ở Java 27.
jdeprscan --release 27 --list --for-removal
~~~

Đây là **lệnh mẫu**, cần có JDK 27 thật và các JAR tương ứng. Trên Windows, classpath phân cách bằng dấu `;` thay vì `:` nếu chỉ định nhiều path.

`jdeprscan` chủ yếu phân tích **tham chiếu tĩnh** tới API deprecated thuộc Java SE được chứa trong bytecode. Nó không tự phát hiện mọi lời gọi thông qua reflection, mã sinh runtime, JNI/native hoặc các deprecation của thư viện bên ngoài Java SE.

Nếu thiếu dependency, phải bổ sung classpath thay vì xem kết quả quét chưa hoàn chỉnh là “không có API deprecated”.

### 4.3. Dùng jdeps để tìm phụ thuộc vào JDK internals

~~~bash
jdeps --jdk-internals --multi-release 27 app.jar
~~~

`jdeps` là công cụ **phân tích dependencies**, không phải bản sao của `jdeprscan`. `--jdk-internals` giúp phát hiện phụ thuộc class-level vào APIs nội bộ mà JDK không cam kết tương thích.

Ví dụ một dependency sử dụng `sun.misc.Unsafe` cần được xem xét riêng, kể cả khi cách sử dụng không xuất hiện dưới dạng deprecation warning ở toàn bộ source của bạn.

### 4.4. Công cụ không thay được kiểm thử runtime

Những đường code sau có thể vượt qua static scanning:

- `Class.forName(nameFromConfig)` và reflective invocation.
- Framework sinh proxy/bytecode.
- Method handles tạo động.
- JNI, FFM và native libraries.
- Serialized data cũ có chứa tên class đã biến mất.
- Driver/framework sử dụng API deprecated trong nhánh hiếm khi chạy.

Vì vậy, nguồn tin cậy cuối cùng là kết hợp **source inspection, binary scanning, integration tests trên Java 27 và quan sát runtime**.

## 5. Lập danh sách migration theo rủi ro thay vì thay hàng loạt

Một bảng theo dõi migration nên có ít nhất:

| Trường | Ý nghĩa |
|---|---|
| API đang dùng | Tên đầy đủ và chữ ký method/type |
| Trạng thái trên JDK 27 | Deprecated / forRemoval / removed / internal |
| Nơi sử dụng | Module, JAR, source path hoặc dependency |
| Thay thế đề xuất | API còn hỗ trợ hoặc thay đổi kiến trúc |
| Semantic risk | Khác về exception, timezone, encoding, identity, lifetime... |
| Test bảo vệ | Unit, integration, binary compatibility, load test |
| Owner | Nhóm sở hữu code/dependency |
| Rollback | Cách quay về release ổn định nếu thay đổi gây lỗi |

Thứ tự ưu tiên:

1. **Đã bị xóa** gây lỗi compile/runtime.
2. **For removal**, đặc biệt tác động bảo mật/tính đúng đắn.
3. API deprecated dẫn tới lỗi logic, bảo mật hoặc compatibility.
4. API deprecated ít rủi ro và có replacement đơn giản.
5. API vẫn hỗ trợ: không tự động thay nếu không có lý do.

Không áp dụng một đợt “replace toàn bộ tên class” khi ý nghĩa nghiệp vụ chưa được xác định. Những thay đổi ngày giờ, charset, I/O và exception thường cần test ranh giới nhiều hơn một phép thay text.

## 6. API mới bị deprecated ở JDK 27: Modifier và AccessFlag

### 6.1. Vì sao các API Modifier bị deprecated?

Java 27 đánh dấu deprecated các method như:

- `Modifier.toString(int)`.
- `Modifier.classModifiers()`, `interfaceModifiers()`, `constructorModifiers()`.
- `Modifier.fieldModifiers()`, `methodModifiers()`, `parameterModifiers()`.

Chúng gắn với mô hình các bit modifier cũ; nhưng **JVM class-file access flags** và **modifiers ở ngôn ngữ Java** không tương đương một-một. Ví dụ `sealed` là language-level modifier không được biểu diễn như một JVM access flag trực tiếp, còn `synthetic` là access flag không tương ứng một modifier Java thông thường.

### 6.2. Thay cách biểu diễn modifier bằng mục tiêu sử dụng

| Bạn thực sự cần | API hiện hành |
|---|---|
| Danh sách JVM access flags của class | `Class.accessFlags()`, kết quả `Set<AccessFlag>` |
| Danh sách access flags của method | `Executable.accessFlags()` |
| Danh sách access flags của field | `Field.accessFlags()` |
| Xem flags hợp lệ tại từng vị trí class-file | `AccessFlag.Location.CLASS/METHOD/FIELD.flags()` |
| Chuỗi mô tả Java-language modifiers của class | `Class.toGenericString()` |
| Chuỗi mô tả khai báo method | `Method.toGenericString()` |
| Kiểm tra đơn giản bit public/private | `Modifier.isPublic(...)` và các method vẫn được hỗ trợ, nếu phù hợp |

**Không** thay mọi lời gọi `Modifier.isPublic(...)` vì chỉ `Modifier.toString(int)` và một số mask helper mới deprecated trong Java 27; kiểm tra trạng thái từng method.

### 6.3. Ví dụ Java 27

~~~java
import java.lang.reflect.AccessFlag;
import java.lang.reflect.Method;
import java.util.Set;

public final class ReflectionFlagsDemo {

    public String greet(String name) {
        return "Xin chào " + name;
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        Class<?> type = ReflectionFlagsDemo.class;

        Set<AccessFlag> classFlags = type.accessFlags();
        System.out.println("Flags: " + classFlags);
        System.out.println("Declaration: " + type.toGenericString());

        Method method = type.getDeclaredMethod("greet", String.class);
        System.out.println("Method flags: " + method.accessFlags());
        System.out.println("Method: " + method.toGenericString());

        Set<AccessFlag> methodLocationFlags =
                AccessFlag.Location.METHOD.flags();

        System.out.println(
                "Possible method flags: " + methodLocationFlags);
    }
}
~~~

Lưu là `ReflectionFlagsDemo.java` khi muốn thử về sau. Đây là ví dụ **JDK 27 API thông thường**, không dùng API preview hoặc phụ thuộc vào class-file internal.

### 6.4. Phân biệt semantics khi migration

`Class.accessFlags()` trả **JVM flags**; `toGenericString()` diễn giải khai báo ở mức ngôn ngữ. Nếu code cũ dùng `Modifier.toString(int)` để tạo một giao diện người dùng hiển thị Java source modifiers, đổi sang in `Set<AccessFlag>` có thể **thay đổi hợp đồng đầu ra**. Chọn API theo yêu cầu thực thay vì thay một-cách-mù-quáng.

## 7. Thay API compiler-tree bị deprecated ở JDK 27

Một số công cụ static analysis, annotation processor hoặc IDE plugin sử dụng `com.sun.source.util.SourcePositions` / `DocSourcePositions`.

Ở JDK 27, những overload:

~~~text
SourcePositions.getStartPosition(CompilationUnitTree, Tree)
SourcePositions.getEndPosition(CompilationUnitTree, Tree)

DocSourcePositions.getStartPosition(CompilationUnitTree,
                                    DocCommentTree, DocTree)
DocSourcePositions.getEndPosition(CompilationUnitTree,
                                  DocCommentTree, DocTree)
~~~

được đánh dấu deprecated. Hướng thay là:

~~~text
SourcePositions.getStartPosition(Tree)
SourcePositions.getEndPosition(Tree)

DocSourcePositions.getStartPosition(DocCommentTree, DocTree)
DocSourcePositions.getEndPosition(DocCommentTree, DocTree)
~~~

### 7.1. Ví dụ cách gọi mới

~~~java
import com.sun.source.tree.Tree;
import com.sun.source.util.SourcePositions;

static long startOffset(SourcePositions positions, Tree tree) {
    return positions.getStartPosition(tree);
}
~~~

Ở đây `positions` đến từ công cụ compiler-tree đang phân tích compilation unit. Với doc-comment AST, dùng `DocSourcePositions` và hai đối số `DocCommentTree` / `DocTree` tương ứng.

### 7.2. Đây là migration đặc thù toolchain

Không cần đưa `SourcePositions` vào một ứng dụng backend bình thường chỉ vì đây là API “mới nhất”. Các thay đổi này quan trọng với tool writers như linter, code analyzer, documentation tool hoặc compiler plugin.

Những công cụ phải hỗ trợ **nhiều phiên bản JDK** cần cân nhắc compile target, runtime version và cách cung cấp adapter tương thích. API mới của Java 27 không tự xuất hiện ở Java 21; code dùng overload mới không chạy nguyên xi trên JDK cũ hơn.

## 8. Reflection: từ Class.newInstance sang Constructor.newInstance

### 8.1. Vì sao Class.newInstance deprecated?

`Class.newInstance()` được đánh dấu deprecated từ JDK 9 vì có thể để checked exception do constructor ném ra **thoát trực tiếp**, làm suy yếu kiểm tra ngoại lệ tại compile time.

Thay bằng:

~~~java
type.getDeclaredConstructor().newInstance();
~~~

API mới mô hình hóa việc khởi tạo qua constructor rõ ràng, bọc lỗi do constructor ném trong `InvocationTargetException`.

### 8.2. Ví dụ độc lập

~~~java
import java.lang.reflect.InvocationTargetException;

public final class ConstructorMigrationDemo {

    public static final class Service {
        public Service() {}

        String label() {
            return "Java 27";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<Service> type = Service.class;

        try {
            Service service = type.getDeclaredConstructor().newInstance();
            System.out.println(service.label());

        } catch (InvocationTargetException error) {
            // Lỗi do constructor thực sự ném.
            Throwable constructorFailure = error.getCause();
            throw new IllegalStateException(
                    "Constructor failed", constructorFailure);
        }
    }
}
~~~

`getDeclaredConstructor()` tìm constructor không tham số; nếu không có, ném `NoSuchMethodException`. Nếu constructor hoặc class không thể truy cập từ caller, có thể ném `IllegalAccessException` hoặc bị ràng buộc JPMS. Không dùng `setAccessible(true)` bừa bãi để bỏ qua encapsulation của module.

### 8.3. Không “gọi được reflection” bằng mọi giá

Nếu code cũ giả định `Class.newInstance()` được phép khởi tạo bất kỳ class nào, migration có thể bộc lộ thiết kế encapsulation sai. Ưu tiên factory method hoặc dependency injection khi có thể.

Thay đổi này còn ảnh hưởng exception contract: test phải kiểm tra `InvocationTargetException.getCause()` thay vì chỉ chờ trực tiếp exception từ constructor như trước.

## 9. Thread.stop đã bị xóa: chuyển sang cooperative cancellation

### 9.1. Vì sao dừng thread cưỡng bức không an toàn?

`Thread.stop()` có thể chấm dứt một thread ở thời điểm nó đang sửa state chia sẻ, để lại invariant không nhất quán. Phương thức này đã bị **loại bỏ trong JDK 26**.

Không có method mới “kill bất kỳ thread Java nào ngay lập tức mà vẫn an toàn”. Mô hình phù hợp là **hủy hợp tác**:

- Caller gửi yêu cầu dừng.
- Worker kiểm tra trạng thái/tín hiệu interrupt ở những điểm phù hợp.
- Worker giải phóng resource và hoàn tất.
- Caller chờ kết thúc với deadline hợp lý.

### 9.2. Thread.interrupt và vòng lặp hợp tác

~~~java
public final class CooperativeWorkerDemo {

    public static void main(String[] args)
            throws InterruptedException {

        Thread worker = Thread.ofVirtual().start(() -> {
            try {
                while (!Thread.currentThread().isInterrupted()) {
                    Thread.sleep(100);
                    // Xử lý một phần công việc ngắn ở đây.
                }
            } catch (InterruptedException interrupted) {
                // Thread.sleep thường xóa interrupt status khi ném.
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Worker cleanup");
            }
        });

        worker.interrupt();
        worker.join();
    }
}
~~~

Thời điểm worker nhận interrupt có thể trước hoặc trong lúc `sleep`; code vẫn có đường kết thúc và cleanup. Ví dụ dùng virtual thread hiện hành, nhưng quy tắc interrupt/cancellation cũng áp dụng với platform thread.

**Không** khẳng định `interrupt()` sẽ cưỡng bức dừng mọi socket/native I/O hay bất kỳ vòng lặp CPU nào. Nếu worker không kiểm tra interrupt và không dùng blocking operations hỗ trợ interruption, nó có thể tiếp tục chạy.

### 9.3. Quản lý theo tác vụ với Future

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

try (ExecutorService executor =
             Executors.newVirtualThreadPerTaskExecutor()) {

    Future<?> task = executor.submit(() -> {
        // Công việc thật cần có contract hủy hợp tác.
    });

    task.cancel(true);
}
~~~

`Future.cancel(true)` biểu thị ý định hủy và có thể yêu cầu interruption tùy implementation/task. `ExecutorService.close()` chờ task kết thúc theo hợp đồng; tránh chỉ dựa vào `try`-with-resources nếu một task có thể block vô hạn và không hợp tác cancellation.

`CompletableFuture.cancel(true)` có semantics khác: tham số `mayInterruptIfRunning` không điều khiển việc interrupt computation bên dưới theo hợp đồng `CompletableFuture`. Không xem mọi loại `Future` giống nhau.

### 9.4. Thread.getId sang threadId

`Thread.getId()` vẫn tồn tại ở Java 27 nhưng deprecated do có thể bị subclass override và trả giá trị không phải thread ID thực.

~~~java
long id = Thread.currentThread().threadId();
~~~

API `threadId()` là lựa chọn hiện hành. Không dùng ID để kiểm tra quyền truy cập hoặc làm định danh toàn cục lâu dài; ID chỉ mang ý nghĩa trong hệ JVM và vòng đời thread theo hợp đồng.

## 10. Object.finalize và quản lý tài nguyên tường minh

### 10.1. Finalization bị đánh dấu loại bỏ

`Object.finalize()` là cơ chế cleanup do GC kích hoạt khi object không còn reachable. Nó **không có deadline bảo đảm**, có thể không chạy trước khi tiến trình kết thúc, có vấn đề security/performance/reliability và đã bị deprecated for removal.

Không dùng finalizer làm đường giải phóng tài nguyên bắt buộc cho file descriptor, socket, native memory hoặc connection database.

### 10.2. Thay bằng AutoCloseable

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public final class ResourceOwnershipDemo {

    static List<String> readLines(Path file) throws IOException {
        // Files.readAllLines tự đóng stream.
        return Files.readAllLines(file);
    }

    static long countLines(Path file) throws IOException {
        try (var lines = Files.lines(file)) {
            return lines.count();
        }
    }

    public static void main(String[] args) throws IOException {
        Path file = Path.of("input.txt");
        // Gọi khi file thực sự có trong môi trường triển khai.
        if (Files.exists(file)) {
            System.out.println(countLines(file));
        }
    }
}
~~~

`Files.lines` trả stream có resource bên dưới; `try`-with-resources đảm bảo đóng khi ra scope, kể cả lúc có exception. Đây là mẫu **quản lý lifetime rõ ràng** thay cho trông chờ GC.

Một lớp tự quản lý resource có thể triển khai `AutoCloseable` / `Closeable` và mô tả ownership cho caller.

### 10.3. Cleaner không phải finalizer mới tương đương một-một

`java.lang.ref.Cleaner` có thể là cơ chế **cleanup dự phòng** cho tài nguyên đặc biệt khi object không còn reachable. Nhưng Cleaner cũng dựa vào reachability/GC, không có deadline, và action cleanup không nên giữ tham chiếu mạnh tới object cần được dọn.

Đường cleanup chính nên là `close()` được gọi có chủ đích. Không thay `finalize()` bằng `Cleaner` rồi tiếp tục giữ thói quen quên đóng tài nguyên.

## 11. SecurityManager: không có drop-in replacement

### 11.1. Trạng thái ở Java 27

Từ JDK 24, Security Manager bị vô hiệu hóa vĩnh viễn. Những API như `System.setSecurityManager(...)` không còn cho phép bật sandbox trong JVM; lời gọi có thể ném `UnsupportedOperationException`. `System.getSecurityManager()` không cung cấp một Security Manager đang hoạt động.

Các type/khái niệm như `SecurityManager`, `AccessController`, `AccessControlContext`, permission policy vốn phục vụ sandbox Java cũ là **deprecated for removal** hoặc không còn semantics ban đầu. Tài liệu chính thức nói **không có replacement trực tiếp** cho Security Manager.

### 11.2. Chọn giải pháp theo mục tiêu bảo mật thật

| Mong muốn ban đầu | Hướng thiết kế hiện hành |
|---|---|
| Hạn chế code không tin cậy đọc file | Chạy trong process/container riêng với OS filesystem permissions |
| Giới hạn network egress | Network policy/firewall/proxy ở hệ điều hành hoặc hạ tầng |
| Phân quyền người dùng nghiệp vụ | Authentication/authorization do ứng dụng/server thực thi |
| Chạy plugin của bên thứ ba | Boundary process, IPC/RPC, API hợp đồng tối thiểu |
| Giữ bí mật production | Secret manager, quyền process tối thiểu, không truyền secrets cho plugin |
| Quan sát hành vi bất thường | Audit/telemetry, sandbox ở mức OS, defense in depth |

`JPMS exports/opens`, `ClassLoader` hoặc `AccessController.doPrivileged` **không** biến thành security sandbox thay thế. Module encapsulation hữu ích cho kiến trúc nhưng không đủ để cô lập mã native/không tin cậy trong cùng tiến trình.

### 11.3. Điều chỉnh logic xác thực khác với bật sandbox

Nếu một thư viện dùng `Subject.getSubject(AccessControlContext)` / `Subject.doAs` cho JAAS trong ngữ cảnh security-manager cũ, cần xem các API hiện hành `Subject.current()` và `Subject.callAs(...)` theo hợp đồng và phạm vi context cụ thể.

Đây là migration riêng của **identity propagation**, không phải cách bật lại Security Manager hoặc thay thế tất cả kiểm soát permission đã mất.

## 12. sun.misc.Unsafe: chọn VarHandle hoặc FFM theo loại thao tác

### 12.1. Không dùng JDK internal API làm nền cho code mới

Các memory-access methods thuộc `sun.misc.Unsafe` không phải Java SE API được hỗ trợ lâu dài. Những method bị đánh dấu deprecated for removal từ JDK 23 có thể phát cảnh báo runtime từ JDK 24 trở đi.

Không nên trấn an rằng “JDK 27 chắc chắn còn Unsafe nên cứ dùng” hoặc yêu cầu người dùng tắt warning vô hạn. Đọc exact deprecation status của method và chủ động lên kế hoạch thay.

### 12.2. Trường hợp trên heap: Atomic/VarHandle

Nếu mục tiêu chỉ là atomic counter:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class Counter {
    private final AtomicInteger value = new AtomicInteger();

    int increment() {
        return value.incrementAndGet();
    }

    int current() {
        return value.get();
    }
}
~~~

Nếu cần atomic field access/điều khiển memory ordering rõ hơn, dùng `VarHandle`:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class VarHandleCounterDemo {

    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup().findVarHandle(
                    VarHandleCounterDemo.class, "value", int.class);
        } catch (ReflectiveOperationException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    void increment() {
        VALUE.getAndAdd(this, 1);
    }

    int current() {
        return (int) VALUE.getVolatile(this);
    }

    public static void main(String[] args) {
        VarHandleCounterDemo counter = new VarHandleCounterDemo();
        counter.increment();
        System.out.println(counter.current()); // 1
    }
}
~~~

`VarHandle` cung cấp nhiều access modes với memory-ordering khác nhau. `getAndAdd` ở ví dụ là thao tác atomic; **không** thay bằng “đọc thường rồi ghi thường” nếu invariant cần tính nguyên tử.

### 12.3. Trường hợp off-heap: FFM

Với native memory, dùng `Arena`, `MemorySegment` và `ValueLayout` của Foreign Function and Memory API:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ForeignMemoryMigrationDemo {
    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_INT);
            segment.set(ValueLayout.JAVA_INT, 0, 27);
            System.out.println(
                    segment.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Phép cấp phát/truy cập qua segment quản lý scope trên là API chính thức hiện hành. Những restricted operations FFM, như liên kết hàm native bằng `Linker.downcallHandle(...)` hoặc diễn giải lại địa chỉ không kiểm chứng, có chính sách **native access** riêng; không tự coi tất cả FFM calls đều cần `--enable-native-access`.

**Không có phép thay một-một** cho mọi thao tác raw memory của Unsafe: cần thiết kế lại bounds, alignment, ownership, thread safety và lỗi lifetime.

## 13. URL constructors deprecated: dùng URI đúng cách

### 13.1. Trạng thái

Các constructor `java.net.URL` đã deprecated từ JDK 20. API khuyến nghị dùng `URI` để parse/khởi tạo, rồi gọi `URI.toURL()` **chỉ khi một API thật sự yêu cầu URL**.

Lý do quan trọng: việc tạo `URL` kiểu cũ có các semantics parse/validation khác nhau giữa protocol handlers. `URI` có cách biểu diễn, escaping và kiểm tra syntax rõ hơn.

### 13.2. Ví dụ Java 27

~~~java
import java.net.URI;
import java.net.URL;
import java.nio.file.Path;

public final class UriMigrationDemo {
    public static void main(String[] args) throws Exception {
        URI endpoint =
                URI.create("https://example.org/api?q=Java%2027");

        // Đa số logic ứng dụng nên tiếp tục dùng URI.
        System.out.println("Host: " + endpoint.getHost());

        // Chỉ đổi khi API cũ bắt buộc nhận URL.
        URL legacyBoundary = endpoint.toURL();
        System.out.println(legacyBoundary);

        // File path chứa dấu cách được chuyển qua URI an toàn.
        URL local = Path.of("report 2027.txt")
                .toAbsolutePath()
                .toUri()
                .toURL();

        System.out.println(local);
    }
}
~~~

Ví dụ **không mở kết nối mạng**. Việc tạo một `URI` hoặc `URL` không chứng minh server tồn tại, TLS an toàn, hoặc địa chỉ được phép truy cập; nếu URL đến từ người dùng, phải kiểm soát SSRF, scheme, host, redirects và DNS re-resolution ở boundary network.

### 13.3. Khác biệt cần test

- `URI.create` có thể ném `IllegalArgumentException` nếu chuỗi URI sai cú pháp.
- `URI.toURL()` có thể ném `MalformedURLException` cho scheme không được hỗ trợ.
- Relative references nên giải bằng `base.resolve(relative)` của `URI` thay vì kỳ vọng constructor `URL(context, spec)`.
- File path phải qua `Path.toUri()`, không nối đường dẫn OS trực tiếp vào chuỗi `file://`.
- URL encoding của các **thành phần** không giống form encoding của toàn bộ URL.

Trong giao thức bên ngoài ứng dụng, cần regression tests cho path có dấu cách, ký tự Unicode, query/fragment, IPv6, authority và các host bị chặn.

## 14. URLEncoder/URLDecoder: chỉ rõ charset và đúng phạm vi

### 14.1. Những overload không có charset đã deprecated

`URLEncoder.encode(String)` và `URLDecoder.decode(String)` sử dụng default charset theo hợp đồng cũ, dẫn đến kết quả có thể khác môi trường.

Dùng overload nhận `Charset`:

~~~java
import java.net.URLEncoder;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public final class FormEncodingDemo {
    public static void main(String[] args) {
        String input = "Java 27 & Việt Nam";

        String encoded = URLEncoder.encode(
                input, StandardCharsets.UTF_8);
        String decoded = URLDecoder.decode(
                encoded, StandardCharsets.UTF_8);

        System.out.println(encoded);
        System.out.println(decoded);
    }
}
~~~

### 14.2. Đây là application/x-www-form-urlencoded

`URLEncoder` không phải bộ mã hóa mọi URL component. Nó biến dấu cách thành `+` theo quy tắc HTML form encoding; sử dụng kết quả để thay toàn bộ URI, path hoặc authority có thể sai.

Khi xây dựng URI phức tạp, cần API tạo URI theo thành phần và phân biệt path segment, query parameter và raw encoding. Khi thay overload cũ, viết test xác nhận byte encoding UTF-8 và round-trip cho dữ liệu Unicode.

### 14.3. Tính tương thích dữ liệu lưu trữ

Nếu hệ thống trước đây đã lưu dữ liệu bằng một charset khác UTF-8, việc đổi sang UTF-8 cho **dữ liệu mới** không tự sửa được lịch sử. Cần kế hoạch migration dữ liệu, xác định charset nguồn và tránh decode/encode chồng hai lần.

## 15. Date/Calendar kiểu cũ và java.time

### 15.1. Đừng nói cả Date đều bị loại bỏ

`java.util.Date` vẫn là type được hỗ trợ, có `Date.from(Instant)` và `toInstant()` để tích hợp API cũ. Tuy nhiên, nhiều constructor và method như `Date.getYear()`, `Date.getMonth()`, `Date.parse(String)` đã deprecated từ lâu.

Với logic nghiệp vụ mới, ưu tiên API `java.time` với kiểu diễn đạt mục đích rõ:

| Nhu cầu | Type thích hợp |
|---|---|
| Một thời điểm trên timeline | `Instant` |
| Chỉ ngày theo lịch | `LocalDate` |
| Thời gian địa phương không gắn zone | `LocalDateTime` |
| Thời điểm gắn zone, có DST rules | `ZonedDateTime` |
| Độ dài thời gian đo theo timeline | `Duration` |
| Khoảng lịch như tháng/năm | `Period` |
| Format/parse có pattern | `DateTimeFormatter` |
| Chuyển tiếp với API nhận `Date` | `Date.from(instant)`, `date.toInstant()` |

### 15.2. Ví dụ ngày giờ có zone tường minh

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Date;

public final class TimeMigrationDemo {

    public static void main(String[] args) {
        LocalDate bookingDay = LocalDate.of(2027, 6, 15);
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        ZonedDateTime start =
                bookingDay.atStartOfDay(zone);

        Instant instant = start.toInstant();

        // Chỉ chuyển khi tích hợp signature cũ nhận Date.
        Date dateForInterop = Date.from(instant);

        System.out.println(dateForInterop.toInstant());
    }
}
~~~

Đừng mặc định `LocalDateTime` có thể chuyển thành `Instant` mà không xác định timezone/offset. Với nghiệp vụ toàn cầu, chuyển đổi có thể làm thay đổi kết quả ở khoảng giao DST; phải test theo zone mục tiêu.

### 15.3. DateTimeFormatter thay parsing mơ hồ

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

DateTimeFormatter formatter =
        DateTimeFormatter.ISO_LOCAL_DATE;

LocalDate date = LocalDate.parse("2027-06-15", formatter);
~~~

Không dùng `Date.parse(String)` cho input không rõ format. Nếu input có nhiều chuẩn, định nghĩa danh sách format hợp lệ, thứ tự thử và xử lý lỗi; không suy đoán ngày/tháng theo locale mặc định.

## 16. Locale constructors deprecated: chọn factory phù hợp

### 16.1. Các lựa chọn Java 27

Các constructor `new Locale("vi", "VN")` đã deprecated, còn:

~~~java
import java.util.Locale;

Locale vietnamese = Locale.of("vi", "VN");
Locale tag = Locale.forLanguageTag("vi-VN");
Locale built = new Locale.Builder()
        .setLanguage("vi")
        .setRegion("VN")
        .build();
~~~

- `Locale.of(...)` hữu ích khi các thành phần ngôn ngữ/khu vực đã được cung cấp riêng.
- `Locale.forLanguageTag(...)` nhận BCP 47 language tag.
- `Locale.Builder` có validation cú pháp khi thiết lập thành phần, phù hợp khi cần phát hiện input không hợp lệ sớm.

`Locale.of(...)` không xác thực nghiêm ngặt tính well-formed của mọi input theo cách `Builder` làm. Không xem chỉ việc thay constructor bằng `of` là đã giải quyết yêu cầu kiểm tra user input.

### 16.2. Locale không phải time zone

`Locale.of("vi", "VN")` chủ yếu mô tả quy ước ngôn ngữ/vùng để format; `ZoneId.of("Asia/Ho_Chi_Minh")` chọn time zone. Không dùng Locale để thay ZoneId trong logic deadline.

Đối với formatter/number currency, luôn thử nghiệm quy tắc hiển thị trên JDK runtime thực vì locale data có thể cập nhật giữa các release.

## 17. Runtime.exec(String): dùng ProcessBuilder

### 17.1. Vấn đề của command string

`Runtime.exec(String)` bị deprecated từ JDK 18 vì tách command thành tokens theo whitespace, dễ sai khi tên file hoặc argument chứa dấu cách. Đừng xem nó là một shell parser đáng tin.

Hướng phù hợp là `ProcessBuilder` hoặc overload `Runtime.exec(String[])`; `ProcessBuilder` thường thuận tiện hơn khi cần thư mục làm việc, environment và redirection.

### 17.2. Đưa từng đối số thành phần tử riêng

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public final class ProcessBuilderMigrationDemo {

    public static void main(String[] args)
            throws IOException, InterruptedException {

        Process process = new ProcessBuilder(
                "java", "-version")
                .redirectErrorStream(true)
                .start();

        try (var output = process.getInputStream()) {
            String text = new String(
                    output.readAllBytes(), StandardCharsets.UTF_8);
            System.out.print(text);
        }

        int exitCode = process.waitFor();
        System.out.println("Exit status: " + exitCode);
    }
}
~~~

`ProcessBuilder` **không tự chạy qua shell** theo nghĩa ghép lệnh shell với pipes/expansion; nếu cần shell pipeline, đó là một lựa chọn riêng, có nguy cơ command injection nếu tạo chuỗi từ input không tin cậy.

Không nối nguyên tham số người dùng vào một chuỗi lệnh rồi truyền cho shell. Truyền từng argument, giới hạn executable được phép, kiểm tra working directory và truyền environment rõ ràng.

### 17.3. Cần quản lý lifecycle và output

Một process có thể:

- Không tồn tại trong `PATH`.
- Trả mã lỗi khác 0.
- Ghi dữ liệu rất lớn ra stdout/stderr.
- Bị treo hoặc không kết thúc.
- Có thứ tự output khác giữa OS.

Ứng dụng cần deadline, xử lý stdout/stderr và dọn process khi hủy. Một ví dụ dùng `waitFor()` không timeout **chỉ thích hợp cho tác vụ đã biết chắc sẽ nhanh và kết thúc**; với process không tin cậy cần `waitFor(timeout, unit)` và chính sách `destroy`/`destroyForcibly` theo contract.

## 18. Wrapper constructors deprecated: factory và parsing

### 18.1. Integer, Long, Double và các wrapper

Một số constructors như `new Integer(42)` hay `new Long("42")` đã deprecated. Thay bằng:

~~~java
int primitive = Integer.parseInt("42");
Integer boxed = Integer.valueOf(42);

long durationMillis = Long.parseLong("1500");
Long boxedLong = Long.valueOf(durationMillis);

double ratio = Double.parseDouble("0.25");
Double boxedDouble = Double.valueOf(ratio);
~~~

Chọn `parseXxx` khi cần primitive, `valueOf` khi cần wrapper. Autoboxing có thể phù hợp, nhưng cần chú ý `null` và việc tự động unbox có thể ném `NullPointerException`.

### 18.2. Khác biệt object identity

Constructor wrapper có thể tạo object mới, trong khi `valueOf` có thể trả object được cache. Không được dùng `==` trên wrapper để diễn tả so sánh giá trị:

~~~java
Integer left = Integer.valueOf(1_000);
Integer right = Integer.valueOf(1_000);

boolean sameValue = left.equals(right);
~~~

Không sửa code để phụ thuộc vào identity của wrapper; đó không phải hợp đồng giá trị mà Java khuyến nghị.

## 19. Runtime.Version và LogRecord: chuyển sang API kiểu rõ hơn

### 19.1. Runtime.Version

Những accessor cũ `Runtime.Version.major()`, `minor()`, `security()` đã deprecated. Version scheme hiện hành có các thành phần:

~~~java
Runtime.Version version = Runtime.version();

int feature = version.feature();
int interim = version.interim();
int update = version.update();
int patch = version.patch();
~~~

Không đoán “major 27” và “minor 0” theo các quy tắc versioning từ thời trước JDK 9. Khi cần feature gating, kiểm tra `version.feature()` với phạm vi version thật mà ứng dụng hỗ trợ.

### 19.2. java.util.logging.LogRecord

`LogRecord.getThreadID()` và `setThreadID(int)` deprecated, trong khi thread ID hiện hành phù hợp `long`:

~~~java
import java.util.logging.Level;
import java.util.logging.LogRecord;

LogRecord record = new LogRecord(Level.INFO, "Started");
record.setLongThreadID(Thread.currentThread().threadId());

long id = record.getLongThreadID();
~~~

Tương tự, `LogRecord.setMillis(long)` có hướng thay `setInstant(Instant)` khi yêu cầu độ chính xác cao.

Không coi Java thread ID là distributed trace ID hoặc security principal. Nếu cần tương quan request xuyên dịch vụ, hãy dùng trace context riêng.

## 20. Những API không có thay thế trực tiếp

### 20.1. Applet đã bị loại bỏ

`java.applet` và `javax.swing.JApplet` đã bị xóa trong JDK 26. Không có một class Java SE 27 thay tên là có thể chạy ứng dụng Applet tương đương trong browser.

Hướng xử lý có thể là:

- Tách business logic khỏi lớp Applet/GUI.
- Thiết kế ứng dụng web với backend Java hoặc desktop app tùy mục tiêu.
- Đánh giá UI, security model, I/O và deployment lại từ đầu.
- Không giữ binary/library cũ rồi hy vọng add module flag để hồi sinh API đã bị xóa.

### 20.2. SecurityManager và app sandbox

Không có direct replacement in-process. Thay đổi kiến trúc và OS isolation là bắt buộc nếu sản phẩm dựa vào khả năng chặn operation của code không tin cậy.

### 20.3. Thread.stop và cưỡng bức kết thúc

Không có “stop an toàn tức thì” trong Java. Có thể cần thiết kế task cancellation, giới hạn I/O và chia process cho công việc không hợp tác.

### 20.4. Unsafe memory internals

Không có mapping đồng nhất cho mọi raw pointer operation. Chọn `VarHandle`/atomics, `MemorySegment`/FFM hoặc library JNI hiện hành theo khả năng và tính đúng đắn.

**Bài học:** “API được hỗ trợ” có thể là một cách thiết kế mới, không chỉ tên phương thức mới.

## 21. Những loại tương thích phải kiểm tra sau migration

### 21.1. Source compatibility

Mã dùng API mới có thể compile trên Java 27 nhưng không compile ở Java 21. Nếu thư viện vẫn cam kết Java 21+, không nên gọi API Java 27 trong source chung mà không có chiến lược multi-release JAR, reflection guard hoặc build tách target.

`--release 21` kiểm tra API Java 21 mà mã có thể dùng. `--release 27` là mục tiêu Java 27; **không** tự bảo đảm chạy trên JVM cũ hơn.

### 21.2. Binary compatibility

Thay signature của public method có thể làm binary clients cũ gặp `NoSuchMethodError`, dù code đã được nâng cấp logic nội bộ thành công. Với library API public, cân nhắc adapter method không deprecated ở caller hoặc bản release major có migration guide.

Ngược lại, giữ phương thức deprecated đang được công bố trong library của mình để tương thích trong một giai đoạn có thể là chiến lược hợp lý, miễn có kế hoạch loại bỏ, documentation và thử nghiệm.

### 21.3. Behavioral compatibility

Một thay đổi nhỏ có thể làm khác:

- Cách parse URL và báo lỗi.
- Múi giờ/format ngày tháng.
- Charset/escaping trong form data.
- Object identity/caching.
- Exception wrapping của reflection.
- Cancellation và việc task thật sự dừng.
- Concurrency/volatile/atomic ordering.
- Security boundary sau khi bỏ SecurityManager.

Test **hành vi** theo hợp đồng, không chỉ test compilation.

### 21.4. Deployment compatibility

Kiểm tra JDK vendor/runtime build, module path, Java agents, FFM/JNI, OS/CPU, container image, TLS, driver versions và flags. Những config như `--add-opens` có thể tạm phục vụ migration reflection nhưng không phải giải pháp lâu dài cho thiết kế encapsulation bị phá.

Không tự bổ sung toàn bộ `--add-opens=...` để che lỗi mà chưa biết component nào đòi deep reflection và vì sao.

### 21.5. Serializations/data contracts

Nếu đổi class/type trong object serialization, định dạng JSON/XML hoặc database mapping, cần xác minh compatibility với dữ liệu cũ.

Ví dụ đổi từ `Date` sang `Instant` trong DTO có thể thay format JSON, timezone representation hoặc schema; adapter ở boundary có thể cần duy trì định dạng cũ cho client trong một giai đoạn.

## 22. Ví dụ tổng hợp: code Java 27 chỉ dùng API còn hỗ trợ

Ví dụ sau tập hợp một số thay đổi dễ áp dụng trong chương trình nhỏ. Lưu thành `ModernApiMigrationDemo.java`. Nó **không cần thư viện ngoài**, không mở kết nối mạng và không dùng Preview.

~~~java
import java.lang.reflect.AccessFlag;
import java.net.URI;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Date;
import java.util.Locale;
import java.util.Set;

public final class ModernApiMigrationDemo {

    public static final class Handler {
        public Handler() {}

        public String process(int value) {
            return "value=" + value;
        }
    }

    public static void main(String[] args) throws Exception {

        // Wrapper: primitive parsing thay constructor deprecated.
        int count = Integer.parseInt("27");

        // Reflection: constructor rõ ràng.
        Handler handler =
                Handler.class.getDeclaredConstructor().newInstance();

        // URL: URI tạo cú pháp, chỉ chuyển sang URL ở boundary.
        URI endpoint =
                URI.create("https://example.org/items?q=Java%2027");
        URL urlForLegacyApi = endpoint.toURL();

        // Form encoding: chỉ rõ charset.
        String form = URLEncoder.encode(
                "Java 27 & Việt Nam", StandardCharsets.UTF_8);

        // Locale và java.time.
        Locale locale = Locale.of("vi", "VN");
        LocalDate date = LocalDate.of(2027, 1, 15);
        Instant startOfDay = date
                .atStartOfDay(ZoneId.of("Asia/Ho_Chi_Minh"))
                .toInstant();

        // Date vẫn được hỗ trợ cho interop.
        Date oldLibraryBoundary = Date.from(startOfDay);

        // Thread ID mới, đồng bộ completion bằng join.
        Thread worker = Thread.ofVirtual().start(
                () -> System.out.println("Worker running"));
        worker.join();

        long threadId = worker.threadId();

        // Classfile flags và mô tả nguồn.
        Set<AccessFlag> flags = Handler.class.accessFlags();
        String declaration = Handler.class.toGenericString();

        System.out.println(handler.process(count));
        System.out.println("URI host = " + endpoint.getHost());
        System.out.println("URL = " + urlForLegacyApi);
        System.out.println("Encoded form = " + form);
        System.out.println("Locale = " + locale);
        System.out.println("Instant = " + oldLibraryBoundary.toInstant());
        System.out.println("Thread id = " + threadId);
        System.out.println("Flags = " + flags);
        System.out.println("Declaration = " + declaration);
        System.out.println("JDK feature = " +
                Runtime.version().feature());
    }
}
~~~

Lệnh tham khảo để biên dịch/chạy với JDK 27:

~~~bash
javac --release 27 \
      -Xlint:deprecation,removal \
      ModernApiMigrationDemo.java

java ModernApiMigrationDemo
~~~

Thứ tự log có thể khác đôi chút nếu worker chưa hoàn tất trước một số thao tác khác, nhưng `worker.join()` bảo đảm worker đã kết thúc trước khi chương trình in các thông tin tiếp theo. Không dùng thứ tự scheduler là assertion bắt buộc trong test.

**Điểm chú ý:** biến `oldLibraryBoundary` là một `Date` còn được hỗ trợ, được tạo bằng factory `Date.from`. Đặt tên để thể hiện tích hợp thư viện có contract Date, **không** hàm ý mọi thứ trong `java.util.Date` đã bị xóa.

## 23. Kế hoạch migration một ứng dụng Java thực tế

### 23.1. Kiểm kê và thiết lập baseline

Trước khi sửa:

~~~text
JDK runtime hiện tại:
JDK 27 target/vendor/build:
Ứng dụng và dependencies:
API deprecated-for-removal:
API removed:
JDK internals:
Các tính năng liên quan bảo mật / native:
Danh sách integration tests và benchmark:
Rollback artifact:
~~~

Ghi lại version JAR, cách chạy (`-cp`, `--module-path`), startup flags và môi trường deployment.

### 23.2. Chia migration thành từng lô nhỏ

Một cách phân nhóm:

1. **Compile blockers:** Applet/Thread.stop hoặc type/method đã bị xóa.
2. **Security/resource correctness:** SecurityManager, finalize, Unsafe, mã native.
3. **API signatures/exception behavior:** reflection, ProcessBuilder, HTTP/URI.
4. **Data semantics:** locale, date/time, charset, serialization.
5. **API hygiene:** wrapper constructors, `Runtime.Version`, logging, JDK27 reflection flags.

Không gom các loại thay đổi này thành một commit khổng lồ nếu hệ thống cần rollback dễ.

### 23.3. Tầng kiểm thử

| Tầng | Ví dụ cần kiểm tra |
|---|---|
| Unit | Parse URI/date, encoding, boundary ở timezone, reflection exceptions |
| Integration | Class loading, module encapsulation, external process, DB/HTTP, native libs |
| Behavioral regression | Thứ tự lỗi, kết quả API và dữ liệu trả cho client |
| Binary compatibility | Library public API không làm downstream clients lỗi linkage |
| Security | Input validation, process isolation, no invalid trust assumptions |
| Performance | Không làm throughput/memory/latency suy giảm đáng kể |
| Deployment smoke | Cùng Java 27 vendor/build và startup flags như production |

Một số migration chỉ có thể kiểm tra đầy đủ trên target OS/architecture tương ứng, nhất là khi có JNI/FFM hoặc external tools.

### 23.4. Không che warning bằng SuppressWarnings vô hạn

`@SuppressWarnings("deprecation")` hoặc `@SuppressWarnings("removal")` có thể hữu ích **tạm thời** tại boundary tương thích mà đội dự án sở hữu và có ticket loại bỏ. Nhưng nếu áp dụng diện rộng để giữ build xanh, hệ thống mất tín hiệu rủi ro.

Hãy ghi rõ lý do, phạm vi, kế hoạch migration và ngày đánh giá lại thay vì dùng suppression như tiêu chuẩn code mới.

### 23.5. Kiểm tra và rollout

~~~mermaid
flowchart TD
    A[Inventory deprecated / for-removal / removed] --> B[Prioritize by risk]
    B --> C[Replace supported APIs or redesign]
    C --> D[Compile with JDK 27 warnings]
    D --> E[jdeprscan + jdeps]
    E --> F[Unit + integration + security tests]
    F --> G[Staging on target runtime]
    G --> H{Compatibility and behavior OK?}
    H -->|No| I[Fix / rollback]
    I --> C
    H -->|Yes| J[Canary + monitoring]
    J --> K[Rollout / retain rollback artifact]
~~~

Nếu một API không có replacement, đó là **thay đổi phạm vi thiết kế**, cần đưa vào kế hoạch sản phẩm thay vì cho rằng compiler flag sẽ giải quyết.

## 24. Checklist trước khi kết luận đã thay xong API

- [ ] Đã ghi lại **tên API và trạng thái chính xác trên JDK 27** (không đoán từ JDK cũ)?
- [ ] Đã phân loại deprecated, forRemoval, removed và internal?
- [ ] Đã ưu tiên các compile/runtime blockers trước?
- [ ] `javac -Xlint:deprecation,removal` không còn cảnh báo ngoài phạm vi chấp nhận?
- [ ] `jdeprscan` đã quét artifact với dependencies phù hợp?
- [ ] `jdeps --jdk-internals` đã phát hiện và phân tích JDK internals?
- [ ] Những lời gọi dynamic/reflection/JNI đã được kiểm thử runtime?
- [ ] Code xử lý thread đã chuyển từ cưỡng bức sang cooperative cancellation nếu cần?
- [ ] Resource cleanup sử dụng ownership/`AutoCloseable`, không dựa vào finalizer?
- [ ] Security controls đã được thiết kế lại nếu trước đây dựa vào SecurityManager?
- [ ] Native memory/concurrency code có kiểm chứng ordering, bounds, lifecycle?
- [ ] URI/URL, form encoding và charset có regression tests?
- [ ] Ngày giờ đã xác định timezone/format rõ ràng?
- [ ] Reflection đã có exception handling phù hợp và không phá JPMS?
- [ ] Public API/library binary compatibility đã được kiểm tra?
- [ ] Không lạm dụng `--add-opens` hoặc `@SuppressWarnings` để che lỗi?
- [ ] Dependencies có phiên bản hỗ trợ JDK 27?
- [ ] CI và production dùng Java runtime đã được xác định vendor/build?
- [ ] Release có quan sát lỗi startup/linkage, rollback và regression tests?
- [ ] Không hứa hỗ trợ Java 21 trong khi code dùng method chỉ có từ Java 27?

## 25. Những lỗi hiểu nhầm thường gặp

| Khẳng định sai | Sửa lại |
|---|---|
| “Deprecated chắc chắn bị xóa ở JDK tiếp theo” | Không có lịch bảo đảm, phải xem forRemoval/JEP/release notes |
| “Đã bị xóa thì chỉ cần tắt warning là chạy” | Compile/linkage không thể hồi sinh API bằng cách tắt warning |
| “Cứ thay toàn bộ deprecated bằng API có tên gần giống” | Phải so sánh semantics, exception, threading, encoding |
| “Toàn bộ `Date` hoặc `File` đều deprecated” | Chỉ những thành viên cụ thể; các type còn được hỗ trợ |
| “`Thread.stop` còn trong Java 27” | Đã bị xóa từ JDK 26 |
| “Có thể bật lại SecurityManager bằng VM flag” | Bị vô hiệu hóa từ JDK 24; không có direct replacement |
| “`Class.newInstance` và `Constructor.newInstance` ném giống nhau” | Constructor exception được bọc vào `InvocationTargetException` |
| “`URL` constructor vẫn là lựa chọn mặc định” | Constructors deprecated; ưu tiên `URI` rồi `toURL` |
| “`URLEncoder` mã hóa mọi URL” | Chỉ HTML form encoding |
| “`Locale.of` tự validate nghiêm ngặt mọi input” | Khi cần validation cú pháp, dùng `Locale.Builder` |
| “`VarHandle` và `Unsafe` hoàn toàn tương đương” | Khác contract và safety; cần thiết kế lại |
| “`ProcessBuilder` tự giải quyết mọi command injection” | Vẫn phải kiểm soát executable/args/env và không ghép shell từ input |
| “`jdeprscan` phát hiện mọi API deprecated” | Nó tập trung Java SE bytecode references; không bao phủ third-party/dynamic |
| “`--release 27` nghĩa là chạy được trên Java 21” | Không; target là Java 27 |
| “Deprecated warning nên bị suppress trên toàn repo” | Mất tín hiệu nâng cấp; chỉ tạm thời ở boundary có kế hoạch |

## 26. Câu hỏi tự kiểm tra

1. `@Deprecated(forRemoval = true)` khác deprecation thông thường như thế nào?
2. Trong Java 27, `Thread.stop()` là deprecated hay đã bị xóa?
3. Vì sao `java.applet` không có replacement Java SE 27 một-một?
4. `jdeprscan` có thể phát hiện deprecation của thư viện thứ ba không?
5. `jdeps --jdk-internals` khác `jdeprscan` như thế nào?
6. Khi dùng `-Werror`, vì sao không nên bật trên toàn monorepo ngay lập tức?
7. Vì sao `Modifier.toString(int)` deprecated ở JDK 27?
8. Khi nào cần `AccessFlag`, khi nào cần `toGenericString()`?
9. Những overload nào của `SourcePositions` bị deprecated ở Java 27?
10. Vì sao `Class.newInstance()` có vấn đề về checked exceptions?
11. Điều gì thay đổi ở cách xử lý exception khi dùng `getDeclaredConstructor().newInstance()`?
12. `Thread.interrupt()` có phải lệnh kill thread an toàn tuyệt đối không?
13. Vì sao `CompletableFuture.cancel(true)` không tương đương `Future.cancel(true)` cho mọi implementation?
14. `Object.finalize()` có bảo đảm dọn tài nguyên trước khi JVM shutdown không?
15. `Cleaner` có thay được `AutoCloseable` cho resource cần đóng chính xác không?
16. Vì sao JPMS không phải security sandbox thay SecurityManager?
17. Khi nào chọn `AtomicInteger`, `VarHandle` và `MemorySegment`?
18. Vì sao `URI.toURL()` phù hợp hơn constructor `URL` khi tích hợp API cần URL?
19. `URLEncoder.encode(text, UTF_8)` có phù hợp để mã hóa toàn bộ URL không?
20. Vì sao một thay đổi từ `Date` sang `Instant` có thể làm thay đổi JSON wire format?
21. `Locale.of` và `Locale.Builder` khác nhau như thế nào về validation?
22. Vì sao `Runtime.exec(String)` gây lỗi với argument chứa dấu cách?
23. Những trường hợp nào làm `Integer.valueOf` khác `new Integer` về object identity?
24. `Runtime.version().feature()` dùng để làm gì khi triển khai nhiều JDK?
25. Vì sao một library compile Java 27 có thể không chạy trên Java 21?
26. Có bao nhiêu tầng tương thích cần test trước khi rollout migration?
27. Nếu replacement không có, cách tiếp cận đúng về sản phẩm và kiến trúc là gì?

## 27. Tài liệu tham khảo chính thức cho Java SE 27

- [Java SE 27 — Deprecated API List](https://docs.oracle.com/en/java/javase/27/docs/api/deprecated-list.html): tình trạng deprecated/forRemoval và gợi ý thay thế theo API.
- [JDK 27 Migration Guide — Removed APIs](https://docs.oracle.com/en/java/javase/27/migrate/removed-apis.html): các API đã bị xóa, bao gồm `Thread.stop` và Applet ở JDK 26, cùng deprecations mới trong JDK 27.
- [Java SE 27 — jdeprscan](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeprscan.html): quét deprecated API references trên bytecode.
- [Java SE 27 — jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html): phát hiện dependencies và JDK internal APIs.
- [Java SE 27 — javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html): `--release`, `-Xlint` và cảnh báo compilation.
- [Java SE 27 API — Modifier](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Modifier.html): deprecation từ Java 27 và migration guidance.
- [Java SE 27 API — AccessFlag](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessFlag.html): JVM access flags và `Location`.
- [Java SE 27 API — Class](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html): `getDeclaredConstructor`, `newInstance` và `accessFlags`.
- [Java SE 27 API — SourcePositions](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.compiler/com/sun/source/util/SourcePositions.html): overload mới không cần `CompilationUnitTree`.
- [Java SE 27 API — DocSourcePositions](https://docs.oracle.com/en/java/javase/27/docs/api/jdk.compiler/com/sun/source/util/DocSourcePositions.html): overload mới cho doc-comment tree.
- [Java SE 27 API — Thread](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Thread.html): `threadId`, interruption và virtual threads.
- [Java SE 27 API — Object](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Object.html): `finalize` deprecated for removal.
- [Java SE 27 API — Cleaner](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ref/Cleaner.html): cleanup dự phòng, không thay ownership tường minh.
- [JEP 421 — Deprecate Finalization for Removal](https://openjdk.org/jeps/421): lý do và các hướng chuyển đổi finalizer.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): trạng thái SecurityManager từ JDK 24.
- [Oracle Java SE 27 — Migrating from JDK 8](https://docs.oracle.com/en/java/javase/27/migrate/migrating-from-jdk-8-later-jdk-releases.html): migration native, security manager, Unsafe và finalization.
- [Java SE 27 API — VarHandle](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes và memory-ordering.
- [Java SE 27 API — MemorySegment](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/foreign/MemorySegment.html): off-heap memory qua FFM.
- [Java SE 27 API — URI](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/URI.html): parse/resolve và `toURL`.
- [Java SE 27 API — URL](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/URL.html): constructor deprecated, chuyển qua URI.
- [Java SE 27 API — URLEncoder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/net/URLEncoder.html): HTML form encoding với Charset.
- [Java SE 27 API — Locale](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html): `of`, `forLanguageTag`, `Builder`.
- [Java SE 27 API — Instant](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/time/Instant.html): thời điểm, zone-safe conversions.
- [Java SE 27 API — ProcessBuilder](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ProcessBuilder.html): khởi động process có argument boundaries rõ ràng.
- [Java SE 27 API — Runtime.Version](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Runtime.Version.html): `feature`, `interim`, `update`, `patch`.
- [Java SE 27 API — LogRecord](https://docs.oracle.com/en/java/javase/27/docs/api/java.logging/java/util/logging/LogRecord.html): `getLongThreadID`, `setLongThreadID` và timestamps.

**Giới hạn của bước viết bài:** Đây là tài liệu Knowledge tập trung vào các API hiện hành của Java SE 27 và ví dụ minh họa, chưa phải kết quả chạy build/CI thực tế hoặc vòng kiểm thử học thuật chuyên sâu. Việc compile, chạy test và so sánh tương thích thư viện được thực hiện ở những bước xác minh tiếp theo của quy trình dự án.
