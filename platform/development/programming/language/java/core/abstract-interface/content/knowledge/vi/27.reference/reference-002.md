# Bảng modifier hợp lệ theo loại thành viên

## Mục tiêu

Java chỉ cho phép một modifier xuất hiện ở những loại khai báo mà ngôn ngữ quy định. Chẳng hạn, trường trong class có thể là private, static, final, transient hoặc volatile; phương thức có thể là abstract, synchronized hoặc native; còn default là modifier dành cho phương thức instance có thân trong interface. Chọn đúng modifier giúp thể hiện quyền truy cập, khả năng kế thừa và cách một thành viên hoạt động.

Bài này dùng quy tắc Java 17 trở lên để tra cứu modifier theo loại khai báo, hiểu modifier ngầm định trong interface, nhận diện các tổ hợp không hợp lệ và đọc lỗi compiler theo đúng nguyên nhân.

## 1. Access modifier và modifier về hành vi

Bốn access level cần phân biệt:

| Modifier | Phạm vi truy cập |
|---|---|
| public | Truy cập từ nơi nhìn thấy được kiểu chứa thành viên và thỏa quy tắc module. |
| protected | Trong cùng package và theo quy tắc kế thừa ở package khác. |
| Không ghi modifier truy cập | Package-private: chỉ trong cùng package. |
| private | Giới hạn trong phạm vi lớp hoặc kiểu bao quanh được Java cho phép. |

Không phải loại khai báo nào cũng dùng được cả bốn access level. Kiểu top-level chỉ có thể là public hoặc package-private; top-level class/interface không thể private hay protected. Constructor và thành viên class có thể dùng public, protected, private hoặc package-private. Thành viên interface có quy tắc riêng: trường và phương thức có modifier ngầm định, còn kiểu thành viên được khai báo trong interface là public static.

Những modifier khác quy định hành vi:

- abstract: để lại phần triển khai cho lớp con hoặc lớp triển khai.
- final: ngăn kế thừa class, ngăn ghi đè phương thức, hoặc ngăn gán lại biến sau khi đã được gán.
- static: thành viên thuộc về kiểu thay vì từng đối tượng; static method được che khuất (hide), không được override theo cơ chế đa hình của instance method.
- sealed và non-sealed: kiểm soát nhánh kế thừa của class hoặc interface.
- transient và volatile: chỉ áp dụng cho trường, nhưng có ý nghĩa khác nhau về tuần tự hóa và truy cập biến.
- synchronized và native: modifier của phương thức.
- default: khai báo hành vi mặc định cho phương thức instance trong interface.
- strictfp: có thể dùng với class, interface và phương thức; từ Java 17, biểu thức dấu phẩy động đã strict theo mặc định nên modifier này thường không cần thiết.

## 2. Bảng modifier theo loại khai báo

| Loại khai báo | Modifier thường được phép | Ghi nhớ |
|---|---|---|
| Top-level class | public, abstract, final, sealed, non-sealed, strictfp; hoặc package-private | Không dùng private, protected hay static. abstract và final loại trừ nhau. |
| Top-level interface | public, abstract, sealed, non-sealed, strictfp; hoặc package-private | Interface ngầm định abstract; không dùng private, protected, final hay static ở cấp top-level. |
| Trường trong class | public, protected, private, static, final, transient, volatile | Chỉ một access modifier; final không thể kết hợp volatile. |
| Phương thức trong class | public, protected, private, abstract, static, final, synchronized, native, strictfp | abstract không thể kết hợp với private, static, final, native, synchronized hoặc strictfp. |
| Constructor | public, protected, private; hoặc package-private | Không dùng static, abstract, final, default, synchronized hay native. |
| Trường trong interface | public, static, final ngầm định | Không dùng private, protected, volatile hoặc transient. |
| Phương thức abstract trong interface | public, abstract ngầm định | Không có thân; không dùng protected, final, synchronized hoặc native. |
| Phương thức default trong interface | default; public ngầm định | Là phương thức instance có thân; không thể đồng thời abstract, static hoặc private. |
| Phương thức static trong interface | static; public ngầm định hoặc private static | Gọi phương thức public static bằng tên interface; helper private chỉ dùng bên trong interface. |
| Phương thức private trong interface | private hoặc private static | Có từ Java 9; phải có thân. |
| Kiểu thành viên trong class | public, protected, private hoặc package-private; static với member class; thêm modifier loại class khi phù hợp | Interface, enum và record lồng nhau là static ngầm định. |
| Kiểu thành viên trong interface | public static ngầm định | Không khai báo kiểu thành viên là private hoặc protected. |
| Biến cục bộ hoặc tham số | final hoặc không có modifier | Không dùng public, private, protected, static, volatile hay transient. Biến effectively final cũng có thể được lambda bắt giữ. |

Bảng này là bản tra cứu nhanh. Một khai báo cụ thể vẫn phải thỏa cả loại thành viên, kiểu bao quanh, vị trí top-level/nested và các tổ hợp loại trừ lẫn nhau.

## 3. Modifier của class và interface

Top-level class có thể là public hoặc package-private, và có thể dùng abstract, final, sealed, non-sealed hoặc strictfp khi thỏa các quy tắc liên quan. Không thể kết hợp abstract với final: abstract dành cho lớp có thể được mở rộng để hoàn thiện phần trừu tượng, còn final cấm kế thừa.

~~~java
public abstract class Task {
    public abstract void run();
}

final class OneShotTask {
    void runOnce() {
        System.out.println("done");
    }
}
~~~

Interface top-level cũng chỉ có thể là public hoặc package-private. Interface ngầm định abstract; ghi rõ abstract là dư thừa nhưng hợp lệ. Interface không thể final vì nó được triển khai bởi class khác, và không thể khai báo static ở cấp top-level.

~~~java
public sealed interface Command permits StartCommand, StopCommand {
    void execute();
}

final class StartCommand implements Command {
    @Override
    public void execute() {
        System.out.println("start");
    }
}

final class StopCommand implements Command {
    @Override
    public void execute() {
        System.out.println("stop");
    }
}
~~~

Ví dụ minh họa sealed hierarchy. Nếu đặt chung trong một tệp nguồn, chỉ một kiểu top-level có thể là public và tên tệp phải khớp với kiểu public. Command giới hạn các kiểu con trực tiếp bằng permits; mỗi kiểu con trực tiếp phải là final, sealed hoặc non-sealed. Modifier non-sealed chỉ hợp lệ khi kiểu đó trực tiếp mở rộng một sealed class hoặc triển khai một sealed interface.

## 4. Modifier của trường

Trường trong class có thể kết hợp access modifier với static, final, transient hoặc volatile nếu tổ hợp cụ thể hợp lệ.

~~~java
class CacheEntry {
    public static final int MAX_SIZE = 100;
    private transient String serializedAway;
    protected volatile boolean refreshNeeded;
    private final String key;

    CacheEntry(String key) {
        this.key = key;
    }
}
~~~

- static final thường dùng cho hằng số thuộc về class. Để là hằng compile-time, giá trị phải là hằng biểu thức phù hợp và kiểu phải là kiểu nguyên thủy hoặc String.
- transient đánh dấu trường không được lưu như một phần trạng thái mặc định khi dùng Java Serialization.
- volatile cung cấp visibility và ordering theo mô hình bộ nhớ Java. Nó không làm cho một chuỗi thao tác nhiều bước trở thành atomic.
- final trên trường yêu cầu gán một lần theo quy tắc definite assignment. Với trường tham chiếu, final khóa việc gán lại tham chiếu chứ không làm đối tượng được tham chiếu tự động bất biến.

Tổ hợp final volatile không hợp lệ. Trường interface luôn là public static final, kể cả khi không viết ba modifier này ra. Do đó, không thể dùng private, protected, volatile hoặc transient để thay đổi cách khai báo trường interface.

## 5. Modifier của phương thức trong class

Các modifier thường gặp là access modifier, abstract, static, final, synchronized, native và strictfp.

- abstract khai báo phương thức không có thân; class chứa phương thức abstract phải là abstract.
- final ngăn lớp con ghi đè phương thức instance.
- static thuộc về class; nó không dùng dispatch đa hình dựa trên kiểu runtime như instance method.
- synchronized đồng bộ thực thi theo monitor của đối tượng đối với instance method, hoặc monitor của class đối với static method.
- native cho biết phần triển khai được cung cấp bên ngoài Java và khai báo không có thân Java.
- strictfp thường không còn cần trong Java 17 vì biểu thức dấu phẩy động đã strict theo mặc định.

Một phương thức abstract không thể đồng thời private, static, final, native, synchronized hoặc strictfp. Những modifier này mâu thuẫn với việc phương thức không có thân cần được triển khai ở lớp con, hoặc bị ngôn ngữ cấm trực tiếp.

~~~java
abstract class Processor {
    protected abstract String transform(String input);

    public final String process(String input) {
        if (input == null) {
            throw new IllegalArgumentException("input must not be null");
        }
        return transform(input);
    }

    public static String version() {
        return "1.0";
    }

    protected synchronized void record() {
        // Cập nhật trạng thái dùng chung một cách đồng bộ.
    }
}
~~~

process là final để giữ nguyên bước kiểm tra đầu vào và cách gọi transform. transform là abstract để lớp con cung cấp cách biến đổi. version là static nên gọi bằng Processor.version(); record là synchronized để đồng bộ thân phương thức trên monitor tương ứng.

## 6. Modifier của phương thức interface

Nếu không phải private, default hoặc static, phương thức interface thông thường là public abstract ngầm định. Interface không cho phép phương thức protected, final, synchronized hoặc native.

~~~java
interface Formatter {
    String format(String input); // public abstract ngầm định

    default String label(String input) {
        return normalize(input);
    }

    static String kind() {
        return "text";
    }

    private String normalize(String input) {
        return input == null ? "" : input.trim();
    }

    private static boolean missing(String input) {
        return input == null || input.isBlank();
    }

    static boolean accepts(String input) {
        return !missing(input);
    }
}
~~~

- format không có thân nên ngầm định public abstract.
- label là phương thức instance có thân; default cho phép lớp triển khai kế thừa hành vi mặc định.
- kind là static và được gọi bằng Formatter.kind(). Phương thức static trong interface không phải phương thức instance được lớp triển khai override.
- normalize là private instance helper; missing là private static helper. Cả hai dạng private method trong interface được hỗ trợ từ Java 9.
- accepts là public static ngầm định vì có static mà không có access modifier private.

Từ khóa default dành cho phương thức instance có thân trong interface. Nó không phải modifier hợp lệ cho phương thức thông thường trong class. Cũng đừng nhầm default method với cú pháp default value của phần tử annotation, nơi từ khóa default dùng theo ngữ pháp riêng.

## 7. Constructor và kiểu thành viên lồng nhau

Constructor chỉ có thể dùng public, protected, private hoặc package-private. Nó không có kiểu trả về và không phải phương thức instance bình thường, vì vậy không dùng static, abstract hay final. Constructor private thường dùng để giới hạn việc tạo đối tượng từ bên ngoài; constructor protected có thể hữu ích cho lớp cơ sở dùng trong kế thừa.

~~~java
public class Factory {
    private Factory() {
    }

    public static Factory create() {
        return new Factory();
    }

    public static abstract class Worker {
        protected abstract void execute();
    }
}
~~~

Factory có constructor private, còn Worker là member class public static abstract. Kiểu thành viên trong class có thể dùng access modifier; member class có thể là static hoặc inner class. Với member interface, enum và record, Java áp dụng các quy tắc static ngầm định và hạn chế riêng của từng loại.

Kiểu thành viên trong interface luôn là public static ngầm định; không thể dùng private hoặc protected để thu hẹp quyền truy cập của kiểu thành viên đó. Record ngầm định final, nên không thêm abstract, sealed hoặc non-sealed vào record.

## 8. Các tổ hợp sai thường gặp

### Access modifier không được phép ở top-level

~~~java
private class Hidden {
}
~~~

Không biên dịch vì top-level class không được private. Nếu cần giới hạn truy cập theo package, bỏ access modifier; nếu cần kiểu chỉ dùng bên trong kiểu khác, khai báo nested class và chọn access modifier phù hợp.

### Kết hợp abstract và final

~~~java
abstract final class Impossible {
}
~~~

Không hợp lệ vì abstract yêu cầu có thể tạo lớp con để hoàn thiện phần trừu tượng, còn final cấm mọi lớp con. Chọn một ý định: abstract cho lớp cơ sở mở rộng hoặc final cho lớp không cho kế thừa.

### Dùng protected trong interface

~~~java
interface BadApi {
    protected void execute();
}
~~~

Không hợp lệ vì phương thức interface không thể protected. Nếu đây là phương thức hợp đồng mà lớp triển khai phải cung cấp, khai báo void execute(); và để nó ngầm định public abstract. Nếu cần helper chỉ dùng bên trong interface, dùng private method có thân.

### Dùng default trong class

~~~java
class OrdinaryClass {
    default void run() {
    }
}
~~~

Không hợp lệ vì default modifier dành cho phương thức instance trong interface. Trong class, dùng access modifier thích hợp và cung cấp thân phương thức bình thường.

### Kết hợp final và volatile cho trường

~~~java
class BadState {
    final volatile int count = 0;
}
~~~

Không hợp lệ vì final ngăn gán lại sau khi khởi tạo, còn volatile áp dụng quy tắc đọc/ghi biến volatile; Java cấm kết hợp hai modifier này trên cùng một trường.

### Khai báo phương thức abstract private

~~~java
abstract class BadProcessor {
    private abstract void process();
}
~~~

Không hợp lệ vì private method không thể được ghi đè để lớp con cung cấp phần triển khai, trái với mục đích của abstract method. Nếu lớp con cần triển khai, dùng protected hoặc public abstract tùy hợp đồng truy cập.

## 9. Ví dụ Java 17 có thể biên dịch và chạy

Lưu toàn bộ mã sau vào tệp ModifierMatrixDemo.java. Ví dụ dùng trường, phương thức class, một lớp trừu tượng lồng nhau và interface có default/static/private methods để minh họa nhiều loại modifier hợp lệ.

~~~java
public class ModifierMatrixDemo {
    protected static final int LIMIT = 10;
    private volatile boolean dirty;
    private transient String cache;

    public synchronized void markDirty() {
        dirty = true;
    }

    protected final int limit() {
        return LIMIT;
    }

    public abstract static class Worker {
        protected abstract String executeTask(String input);

        public final String execute(String input) {
            if (input == null || input.isBlank()) {
                throw new IllegalArgumentException("input must not be blank");
            }
            return executeTask(input);
        }
    }

    public interface Plugin {
        int API_VERSION = 1;

        default String name() {
            return normalize(" plugin ");
        }

        static int apiVersion() {
            return API_VERSION;
        }

        static boolean supported(String candidate) {
            return !isBlank(candidate);
        }

        private String normalize(String value) {
            return value.trim();
        }

        private static boolean isBlank(String value) {
            return value == null || value.isBlank();
        }
    }

    private static final class UppercaseWorker extends Worker {
        @Override
        protected String executeTask(String input) {
            return input.toUpperCase(java.util.Locale.ROOT);
        }
    }

    private static final class DemoPlugin implements Plugin {
    }

    public static void main(String[] args) {
        Worker worker = new UppercaseWorker();
        System.out.println(worker.execute("java"));

        Plugin plugin = new DemoPlugin();
        System.out.println(plugin.name());
        System.out.println(Plugin.apiVersion());
        System.out.println(Plugin.supported("demo"));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac ModifierMatrixDemo.java
java ModifierMatrixDemo
~~~

Kết quả stdout chính xác:

~~~text
JAVA
plugin
1
true
~~~

Ví dụ cho thấy protected static final là tổ hợp trường hợp lệ; volatile dùng cho trạng thái mutable; synchronized là modifier phương thức; final giữ nguyên phương thức limit và execute khỏi bị ghi đè; abstract bắt lớp con triển khai executeTask. Trong Plugin, API_VERSION ngầm định public static final, name là default method, apiVersion và supported là static method, còn normalize và isBlank là helper private. Các lớp lồng nhau dùng private static final hoặc public static abstract theo mục đích của chúng.

## 10. Cách đọc lỗi compiler và checklist

Khi compiler báo modifier không hợp lệ, hãy kiểm tra theo trình tự:

1. Loại khai báo: top-level type, nested type, field, method, constructor hay local variable?
2. Access level: loại khai báo này có cho phép public, protected hoặc private không?
3. Modifier theo loại: transient chỉ dành cho field, synchronized dành cho method, sealed/non-sealed dành cho class hoặc interface.
4. Tổ hợp xung đột: abstract với final/private/static/native/synchronized; final với volatile; hoặc default trong class thông thường.
5. Ngữ cảnh kế thừa: sealed/non-sealed chỉ hợp lệ khi quan hệ với sealed parent thỏa quy tắc; abstract method phải được lớp concrete triển khai.
6. Modifier ngầm định: field interface đã public static final; phương thức interface thông thường đã public abstract; member type trong interface đã public static.
7. Phiên bản Java: private interface methods cần Java 9 trở lên; ví dụ bài này nhắm Java 17+.

Không nên thêm modifier chỉ vì nó xuất hiện ở một khai báo khác gần giống. Java phân biệt loại khai báo và ngữ cảnh: modifier hợp lệ cho field có thể sai với method; modifier hợp lệ cho member class có thể sai với top-level class; và modifier của interface không luôn giống modifier của class.

## Kết luận

Bảng modifier chỉ hữu ích khi đọc cùng loại khai báo và ngữ cảnh chứa nó. Hãy xác định loại thành viên, kiểm tra access level, sau đó kiểm tra modifier hành vi và các tổ hợp xung đột. Hiểu modifier ngầm định của interface, khác biệt giữa phương thức class và interface, cùng quy tắc sealed hierarchy giúp viết API Java đúng cú pháp, dễ đọc và có chủ đích hơn.