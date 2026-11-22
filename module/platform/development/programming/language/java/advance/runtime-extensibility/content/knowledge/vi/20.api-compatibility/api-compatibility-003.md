# Phương thức default, xung đột kế thừa và tiến hóa hợp đồng dịch vụ

Trong một nền tảng plugin Java, **host và các provider thường được phát hành độc lập**. Host định nghĩa interface dịch vụ, còn các plugin bên thứ ba triển khai interface ấy rồi được nạp thông qua ServiceLoader hoặc một plugin manager riêng. Khi interface cần thêm khả năng, sửa hợp đồng tưởng như đơn giản có thể khiến plugin cũ không biên dịch được, hành vi thay đổi âm thầm hoặc thậm chí gây lỗi liên kết khi chạy.

Java hỗ trợ **default method** trong interface để cung cấp hành vi mặc định cho cả những class không tự cài đặt phương thức đó. Đây là công cụ tiến hóa API hữu ích, nhưng **không đồng nghĩa thêm default method luôn an toàn**. Xung đột kế thừa giữa các interface, khác biệt giữa tương thích source/binary/behavior và class identity vẫn phải được xem xét.

Bài này giải thích quy tắc phân giải method trên Java 17+, xây hai thí nghiệm có thể biên dịch: một chương trình cho các quy tắc kế thừa và một plugin JAR **được biên dịch với API v1** nhưng chạy cùng host **biên dịch với API v2**. Một thí nghiệm cuối tái hiện tình huống mã nhị phân cũ gặp xung đột default ở runtime.

## 1. Hiểu đúng ba lớp tương thích API

Khi nâng cấp SPI/interface, cần phân biệt:

| Loại tương thích | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Source compatibility** | Mã nguồn plugin cũ có biên dịch lại được với API mới không? | Class cũ implements hai interface nay đều có default cùng signature có thể bị javac từ chối |
| **Binary compatibility** | File .class đã biên dịch với API cũ có thể liên kết với API mới theo quy tắc JVM không? | Thêm default method là thay đổi tương thích nhị phân theo JLS, nhưng một invocation có thể gặp IncompatibleClassChangeError |
| **Behavioral compatibility** | Dù nạp và gọi được, kết quả/side effect/error contract có còn đúng kỳ vọng? | Default supports(...) quá rộng khiến host chọn provider cũ cho khả năng nó chưa thực sự hỗ trợ |

**Binary-compatible không phải là lời hứa mọi invocation sẽ thành công.** Đặc biệt, JLS §13.5.7 nêu rõ việc thêm default method hoặc đổi abstract thành default thường giữ tương thích nhị phân với class đã có, nhưng trong một số xung đột thừa kế có thể gây IncompatibleClassChangeError **khi phương thức được gọi**. Mã nguồn tương ứng khi biên dịch lại có thể báo lỗi sớm hơn.

**Source-compatible cũng không đảm bảo behavioral-compatible.** Nếu API v2 tự mặc định một thao tác ghi dữ liệu mà API v1 chưa từng hứa, plugin cũ có thể "chạy được" nhưng làm sai nghiệp vụ. Vì vậy nên đánh giá default method bằng cả ba tầng, không chỉ kiểm tra javac không báo lỗi.

## 2. Default method hoạt động như thế nào?

Interface có thể khai báo một phương thức instance với **default** và phần thân:

~~~java
public interface MessageService {
    String transform(String input); // Phương thức abstract bắt buộc.

    default boolean supportsAdvanced() {
        return false;               // Hành vi bảo thủ dành cho provider cũ.
    }
}
~~~

Đoạn trên là interface độc lập về cú pháp, chưa phải toàn bộ chương trình chạy. Một class triển khai MessageService chỉ bắt buộc viết transform(String). Nếu không tự override supportsAdvanced(), nó được hưởng implementation mặc định trả false.

Default method có những thuộc tính quan trọng:

- Là **instance method** thuộc interface, không phải static utility method và không phải constructor.
- Có phần thân và có thể gọi các phương thức abstract khác của interface qua this, miễn kiểu/kết quả phù hợp.
- Khi class cung cấp một implementation override hợp lệ, class đó được dùng thay cho default.
- **Không thêm một abstract method mới vào nghĩa vụ của provider cũ** như cách thêm phương thức abstract thông thường.
- Có thể bị override trong subinterface hoặc concrete class; cú pháp InterfaceName.super.method() dùng được ở nơi có direct superinterface phù hợp để gọi một implementation default đã biết.
- Không thể định nghĩa default method có signature override-equivalent với một public instance method của Object, ví dụ default String toString() hoặc default boolean equals(Object). Interface vẫn có thể khai báo phương thức abstract tương ứng hoặc phương thức helper với tên khác theo quy tắc ngôn ngữ.
- Method static của interface và private helper method (Java 9+) có vai trò riêng; static method không trở thành instance method được kế thừa như default.

Một lựa chọn mặc định như **supportsAdvanced() = false** có giá trị chiến lược: provider chưa chủ động nâng cấp sẽ không quảng cáo một capability mới. Mặc định **true** có thể dễ viết hơn nhưng chỉ an toàn khi chắc chắn tất cả implementation hiện có đều thực sự đáp ứng hành vi đó.

## 3. Quy tắc phân giải kế thừa default

Khi nhiều nguồn có phương thức cùng signature, Java không đơn giản "lấy interface đứng trước". Có bốn tình huống nền tảng.

### 3.1. Phương thức từ class thắng default của interface

Nếu superclass đã có instance method phù hợp, class method có ưu tiên cao hơn default method được kế thừa từ interface.

~~~java
class Base {
    public String name() {
        return "base";
    }
}

interface Named {
    default String name() {
        return "interface";
    }
}

class Concrete extends Base implements Named {
    // Không cần override name().
}
~~~

Ở đây new Concrete().name() cho kết quả **base**. Quy tắc này thường gọi ngắn gọn là **class wins**. Với abstract class method cùng signature, không được hiểu rằng default của interface tự động xóa nghĩa vụ implement abstract method của class; concrete subclass vẫn phải thỏa các quy tắc override của Java.

Điểm cần kiểm tra khi nâng cấp API: một plugin class có public method trùng signature với default mới **có thể vô tình override** default ấy và dùng hành vi riêng đã có từ trước. Không có xung đột compile-time chưa chắc hành vi mới đúng ý tác giả interface.

### 3.2. Subinterface chuyên biệt hơn có quyền override

~~~java
interface ParentName {
    default String name() {
        return "parent";
    }
}
interface ChildName extends ParentName {
    @Override
    default String name() {
        return "child";
    }
}
class Specific implements ChildName {}
~~~

new Specific().name() trả **child**. ChildName là subinterface chuyên biệt hơn và đã override default của ParentName; đây không phải xung đột giữa hai interface không liên quan.

Nếu một interface được kế thừa qua hai đường nhưng cùng đi tới **một khai báo default duy nhất**, bản thân hình thoi kế thừa không nhất thiết gây lỗi. Vấn đề là **những khai báo khác nhau có signature tương đương mà không có quan hệ override rõ ràng**.

### 3.3. Hai default không liên quan gây lỗi biên dịch

~~~java
interface AuditName {
    default String name() {
        return "audit";
    }
}
interface MetricName {
    default String name() {
        return "metric";
    }
}

// MÃ CỐ TÌNH SAI, KHÔNG biên dịch:
class Conflicted implements AuditName, MetricName {}
~~~

Cả AuditName và MetricName khai báo default name() cùng signature, không interface nào chuyên biệt hơn interface kia. Concrete class Conflicted phải chủ động giải quyết, thay vì Java chọn tùy thứ tự implements.

Cách sửa đúng:

~~~java
class Resolved implements AuditName, MetricName {
    @Override
    public String name() {
        return AuditName.super.name()
                + "+" + MetricName.super.name();
    }
}
~~~

Đây là code thay thế cho Conflicted trong cùng ngữ cảnh đã khai báo AuditName và MetricName; không để cả class lỗi biên dịch trong chương trình build. Ở Resolved, lời gọi đến từng default được viết rõ, rồi host tự quyết định cách kết hợp. Hoàn toàn có thể chọn chỉ một default hoặc triển khai logic mới, miễn đáp ứng hợp đồng.

**Không thể sửa bằng cách đảo thứ tự implements**. Java không dùng vị trí của interface trong danh sách để phân xử hai default xung đột.

### 3.4. Một abstract và một default không liên quan vẫn có thể xung đột

~~~java
interface A {
    default void execute() {}
}
interface B {
    void execute();
}

// MÃ CỐ TÌNH SAI: cần giải quyết xung đột kế thừa.
abstract class Unresolved implements A, B {}
~~~

Khi một interface/class kế thừa đồng thời các phương thức override-equivalent từ hai superinterface không liên quan, một bên default và bên kia abstract **không được giả định default tự động làm implementation cho abstract kia**. Đây cũng là tình huống cần override rõ ràng:

~~~java
class Fixed implements A, B {
    @Override
    public void execute() {
        A.super.execute();
    }
}
~~~

Việc lựa chọn delegate cho A.super.execute() là **quyết định semantic**. Đôi khi B đặt ra điều kiện mà implementation của A không đáp ứng; khi ấy cần viết logic riêng chứ không gọi default chỉ để javac chấp nhận.

JLS §9.4.1.3 mô tả quy tắc tương đương chữ ký khi kế thừa nhiều phương thức. Những tình huống phức tạp hơn còn phụ thuộc erasure, covariant returns, generic methods, bridge methods và accessibility; phải kiểm tra actual signature ở cả source lẫn bytecode trước khi thay API.

## 4. Chương trình Java 17+ thực nghiệm các quy tắc

Tạo file **DefaultRulesDemo.java** với nội dung hoàn chỉnh sau:

~~~java
import java.util.Locale;

public final class DefaultRulesDemo {
    interface MessageService {
        String transform(String input);

        default boolean supportsAdvanced() {
            return false;
        }
    }

    static class LegacyPlugin implements MessageService {
        @Override
        public String transform(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    static final class NewPlugin extends LegacyPlugin {
        @Override
        public boolean supportsAdvanced() {
            return true;
        }
    }

    interface Audit {
        default String label() {
            return "audit";
        }
    }

    interface Metric {
        default String label() {
            return "metric";
        }
    }

    static final class Combined implements Audit, Metric {
        @Override
        public String label() {
            return Audit.super.label() + "+" + Metric.super.label();
        }
    }

    static class ParentClass {
        public String label() {
            return "class";
        }
    }

    interface Tagged {
        default String label() {
            return "interface";
        }
    }

    static final class ClassWins
            extends ParentClass implements Tagged {}

    interface Parent {
        default String label() {
            return "parent";
        }
    }

    interface Child extends Parent {
        @Override
        default String label() {
            return "child";
        }
    }

    static final class MostSpecific implements Child {}

    public static void main(String[] args) {
        MessageService legacy = new LegacyPlugin();
        MessageService modern = new NewPlugin();

        System.out.println("legacy=" + legacy.transform("hello"));
        System.out.println("legacy-advanced="
                + legacy.supportsAdvanced());
        System.out.println("modern=" + modern.transform("world"));
        System.out.println("modern-advanced="
                + modern.supportsAdvanced());

        System.out.println("combined=" + new Combined().label());
        System.out.println("class-wins=" + new ClassWins().label());
        System.out.println("specific=" + new MostSpecific().label());
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 DefaultRulesDemo.java
java DefaultRulesDemo
~~~

**Stdout kỳ vọng chính xác:**

~~~text
legacy=HELLO
legacy-advanced=false
modern=WORLD
modern-advanced=true
combined=audit+metric
class-wins=class
specific=child
~~~

Giải thích từng nhóm kết quả:

- LegacyPlugin chỉ implement transform, nhưng gọi supportsAdvanced được qua default. Nó nhận false, không tự tuyên bố hỗ trợ tính năng mới.
- NewPlugin kế thừa implementation transform và override supportsAdvanced thành true. Đây là **opt-in rõ ràng**.
- Combined bắt buộc quyết định giữa Audit và Metric, rồi gọi hai default bằng Audit.super và Metric.super.
- ClassWins kế thừa label() của ParentClass; phương thức class được chọn thay vì Tagged.default.
- MostSpecific nhận label() từ Child vì Child override Parent.

Chương trình này chạy trong một compilation unit với các interface và class là **nested types**, thuận tiện thử nghiệm. Trong plugin thật, interface API nên là public top-level type thuộc artifact chung, không đặt bên trong class demo.

## 5. Vì sao default có thể giúp tiến hóa hợp đồng dịch vụ?

Giả sử một platform ban đầu chỉ định nghĩa:

~~~java
// API v1: demo.api.TextService
package demo.api;

public interface TextService {
    String apply(String text);
}
~~~

Các plugin v1 đã build cung cấp apply. Đến API v2, host muốn hỏi provider có hỗ trợ chế độ nâng cao hay không. Nếu thêm:

~~~java
// API v2: demo.api.TextService
package demo.api;

public interface TextService {
    String apply(String text);

    default boolean supportsAdvanced() {
        return false;
    }
}
~~~

Đối với class provider v1 **không bị xung đột phương thức**, default cho phép host v2 gọi supportsAdvanced() dù plugin class chưa từng được biên dịch lại. Host có thể tiếp tục dùng apply(...) cho những provider cũ. Đây là lợi ích quan trọng khi triển khai plugin độc lập.

Tuy nhiên, có ba câu hỏi phải trả lời:

1. **Tên/signature mới có xung đột với method public nào của provider hoặc interface khác không?** Nếu provider có phương thức cùng tên nhưng kiểu trả về không tương thích, compile lại có thể lỗi; nếu thêm một default tương đương trong interface không liên quan, có thể xảy ra conflict.
2. **Mặc định có đúng nghiệp vụ không?** Với capability mới, trả false hoặc một hành vi no-op có contract rất rõ thường an toàn hơn tự ý bật tính năng.
3. **API v2 có thực sự được nạp tại runtime không?** Một plugin manager/class loader có thể tải nhầm API v1 từ JAR khác; client v2 gọi phương thức không tồn tại trong interface runtime sẽ có nguy cơ NoSuchMethodError. Default không sửa được lỗi classpath/class identity.

Cần giữ nguyên **binary name** của interface, tên method và descriptor của method hiện có để không phá caller cũ. Đổi kiểu tham số, kiểu trả về, static/instance hoặc xóa một method không phải chuyện "tăng minor version" đơn giản; phải có kế hoạch migration và kiểm chứng bytecode.

## 6. Thí nghiệm hai phiên bản: plugin cũ, host mới

Thí nghiệm sau thật sự biên dịch **plugin-old.jar dựa vào api-v1.jar**, rồi không build lại plugin. Tiếp đó chỉ biên dịch host bằng api-v2.jar và chạy với bản API v2. Nhờ vậy ta kiểm tra compatibility của **binary cũ**, không chỉ việc cùng compile source một lần.

### 6.1. Cây file

Các đường dẫn tính từ thư mục **spi-evolution/**:

~~~text
spi-evolution/
├── api-v1/demo/api/TextService.java
├── api-v2/demo/api/TextService.java
├── plugin/demo/plugin/UpperPlugin.java
├── host/demo/host/Host.java
├── resources/META-INF/services/demo.api.TextService
├── build/                          (tạo bởi javac)
└── dist/                           (tạo bởi jar)
~~~

Hai file TextService.java có **cùng package và binary name**, nhưng ở hai thư mục độc lập. Ta chỉ đưa **một version API tại một thời điểm** lên classpath biên dịch hoặc runtime. Không đóng gói cả api-v1.jar và api-v2.jar cùng lúc để "Java tự chọn bản mới".

### 6.2. API v1

File **api-v1/demo/api/TextService.java**:

~~~java
package demo.api;

public interface TextService {
    String apply(String text);
}
~~~

### 6.3. API v2 bổ sung default

File **api-v2/demo/api/TextService.java**:

~~~java
package demo.api;

public interface TextService {
    String apply(String text);

    default boolean supportsAdvanced() {
        return false;
    }
}
~~~

Lưu ý **apply(String)** không đổi signature giữa hai version. V2 chỉ bổ sung một method instance có implementation mặc định.

### 6.4. Provider được build duy nhất với API v1

File **plugin/demo/plugin/UpperPlugin.java**:

~~~java
package demo.plugin;

import demo.api.TextService;
import java.util.Locale;

public final class UpperPlugin implements TextService {
    public UpperPlugin() {}

    @Override
    public String apply(String text) {
        return text.toUpperCase(Locale.ROOT);
    }
}
~~~

File **resources/META-INF/services/demo.api.TextService** chứa một dòng:

~~~text
demo.plugin.UpperPlugin
~~~

Descriptor SPI classpath có tên **đầy đủ của interface**; nội dung là tên binary của implementation. Plugin JAR **không chứa bản sao TextService.class**: API phải được cung cấp từ classpath chung của host. Constructor public không tham số cho phép ServiceLoader trên classpath tạo provider.

### 6.5. Host biên dịch với API v2

File **host/demo/host/Host.java**:

~~~java
package demo.host;

import demo.api.TextService;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        int providers = 0;

        for (TextService provider :
                ServiceLoader.load(TextService.class)) {
            System.out.println("provider="
                    + provider.getClass().getName());
            System.out.println("basic=" + provider.apply("hi"));
            System.out.println("advanced="
                    + provider.supportsAdvanced());
            providers++;
        }
        System.out.println("count=" + providers);
    }
}
~~~

Host chỉ biết interface TextService v2. Nó không compile-time import UpperPlugin và không gọi class implementation bằng tên cụ thể.

### 6.6. Các lệnh build theo đúng thứ tự version

Dùng JDK 17+ và shell bash/POSIX, đứng tại **spi-evolution/**:

~~~bash
mkdir -p build/api-v1 build/api-v2 build/plugin build/host dist

javac --release 17 -encoding UTF-8 -d build/api-v1 api-v1/demo/api/TextService.java
jar --create --file dist/api-v1.jar -C build/api-v1 .

# Plugin cũ: biên dịch với API v1.
javac --release 17 -encoding UTF-8 -cp dist/api-v1.jar -d build/plugin plugin/demo/plugin/UpperPlugin.java
jar --create --file dist/plugin-old.jar -C build/plugin . -C resources .

# API mới và host mới: không biên dịch lại plugin-old.jar.
javac --release 17 -encoding UTF-8 -d build/api-v2 api-v2/demo/api/TextService.java
jar --create --file dist/api-v2.jar -C build/api-v2 .
javac --release 17 -encoding UTF-8 -cp dist/api-v2.jar -d build/host host/demo/host/Host.java

# Runtime chỉ có API v2 và JAR plugin cũ.
java -cp "build/host:dist/api-v2.jar:dist/plugin-old.jar" demo.host.Host
~~~

**Stdout kỳ vọng chính xác:**

~~~text
provider=demo.plugin.UpperPlugin
basic=HI
advanced=false
count=1
~~~

Ở thời điểm biên dịch UpperPlugin, method supportsAdvanced() **chưa tồn tại**. Tại runtime, JVM thấy TextService API v2 và provider đã compile từ v1. Provider không override method mới, nên lời gọi lấy implementation default trả false.

Trên Windows trong PowerShell/CMD, dấu phân cách classpath là dấu **;** thay vì **:**; các lệnh mkdir -p là cú pháp bash. Thư mục và file phải đúng các đường dẫn đã nêu; không thêm một bản TextService.class trùng lặp trong plugin-old.jar.

Lệnh kiểm tra:

~~~bash
jar --list --file dist/api-v2.jar
jar --list --file dist/plugin-old.jar
javap -public -classpath dist/api-v2.jar demo.api.TextService
javap -public -classpath dist/plugin-old.jar demo.plugin.UpperPlugin
~~~

Tìm TextService.class trong **api-v2.jar**, UpperPlugin.class và META-INF/services/demo.api.TextService trong **plugin-old.jar**. javap ở API v2 cho thấy supportsAdvanced(); javap ở plugin-old không liệt kê một implementation mới do compiler tự chèn vào plugin, vì default thuộc **interface runtime**.

Đây là thí nghiệm **binary reuse**, không phải chứng minh tất cả thay đổi default của mọi API đều an toàn. Nó cố ý chỉ có một interface, không có conflict tên phương thức và không có dependencies khác.

## 7. Default collision khi nâng cấp: tình huống nguy hiểm hơn

### 7.1. Source collision

Xem plugin từ bên thứ ba:

~~~java
interface Red {
    default String label() {
        return "red";
    }
}
interface Blue {
    default String label() {
        return "blue";
    }
}

// Không biên dịch được nếu Red và Blue không có quan hệ override.
class Dual implements Red, Blue {}
~~~

Nếu trước đây Blue không có label(), class Dual cũ có thể đã biên dịch hợp lệ và sử dụng Red.label(). Khi tác giả Blue **thêm default label()**, việc biên dịch lại Dual có thể bị lỗi vì class kế thừa hai method không tương thích từ hai interface không liên quan.

Điều tương tự có thể xảy ra với một public method trong thư viện khác có signature giống method vừa được thêm. Kiểm thử migration phải có các tổ hợp interface thực tế mà plugin của bên thứ ba đang implements, không chỉ class mẫu do host sở hữu.

### 7.2. Binary collision với plugin class chưa biên dịch lại

Java SE 17 JLS §13.5.7 đưa ví dụ: **thêm default method** được định nghĩa là thay đổi binary-compatible, nhưng khi binary cũ tham chiếu method trong một tình huống tồn tại hai default xung đột, invocation có thể ném **IncompatibleClassChangeError**.

Bài lab tái hiện độc lập bằng việc thay duy nhất Right.class ở runtime, để **Both.class và Run.class vẫn là binary cũ**. Thư mục gốc ví dụ **binary-clash/**:

~~~text
binary-clash/
├── old/Left.java
├── old/Right.java
├── old/Both.java
├── old/Run.java
├── new/Right.java
└── build/                (tạo khi biên dịch)
~~~

File **old/Left.java**:

~~~java
public interface Left {
    default String name() {
        return "left";
    }
}
~~~

File **old/Right.java**:

~~~java
public interface Right {
}
~~~

File **old/Both.java**:

~~~java
public final class Both implements Left, Right {
}
~~~

File **old/Run.java**:

~~~java
public final class Run {
    public static void main(String[] args) {
        System.out.println(new Both().name());
    }
}
~~~

File **new/Right.java**:

~~~java
public interface Right {
    default String name() {
        return "right";
    }
}
~~~

Các file này đặt trong **default package** chỉ để giữ ví dụ ngắn và dễ nhìn binary upgrade; sản phẩm thực nên dùng package theo namespace ổn định.

Biên dịch bản cũ trước, sau đó biên dịch **chỉ một interface bản mới**:

~~~bash
mkdir -p build/old build/new

javac --release 17 -encoding UTF-8 -d build/old old/*.java
java -cp build/old Run

javac --release 17 -encoding UTF-8 -d build/new new/Right.java
java -cp "build/new:build/old" Run
~~~

Lần chạy đầu in chính xác:

~~~text
left
~~~

Lần chạy thứ hai **dự kiến thất bại với IncompatibleClassChangeError tại invocation** khi JVM phải phân giải các default name() từ Left và Right không có quan hệ ưu tiên. Thông điệp chi tiết và stack trace của lỗi có thể khác giữa các bản JDK, nên **không có stdout cố định** cho lần chạy lỗi. Tên Right.class mới nằm ở đầu classpath, còn Both.class và Run.class cũ giữ nguyên.

Nếu thay vì giữ binary cũ bạn thử **biên dịch lại Both.java với Right mới**, javac sẽ báo xung đột kế thừa sớm hơn. Đây là khác biệt quan trọng giữa **source compatibility** và **binary compatibility có lỗi ở lúc gọi**.

Có một cách sửa chính thức: sửa code của Both để triển khai/override name() một cách minh bạch, rồi rebuild provider. Nếu không kiểm soát source của plugin cũ, nhà phát triển API phải cân nhắc **đổi tên method mới, dùng extension interface riêng hoặc rollback default đã gây conflict**. Không nên giải quyết bằng cách đảo thứ tự classpath không kiểm soát, vì điều đó chỉ chọn nhầm API version khác.

## 8. Chọn cách tiến hóa SPI: default hay extension interface?

Một service contract có thể tăng chức năng theo nhiều phương án:

**Cách A — thêm default bảo thủ:** dùng khi có fallback **đúng semantics** và host có thể hoạt động hợp lệ với plugin chưa nâng cấp. Ví dụ supportsAdvanced() trả false. Ưu điểm là giữ runtime compatibility cho provider cũ ở các trường hợp không có method collision.

**Cách B — tạo extension interface:** nếu capability thật sự mới, không thể cung cấp implementation mặc định an toàn, có thể khai báo interface mới kế thừa interface gốc:

~~~java
// Mã minh họa: đây là các top-level interface ở các file riêng.
public interface TextService {
    String apply(String input);
}

public interface BatchTextService extends TextService {
    java.util.List<String> applyBatch(
            java.util.List<String> inputs);
}
~~~

Đoạn trên chỉ minh họa **hai file khác nhau**, không thể đặt nguyên cả hai public top-level interface vào cùng một file .java. Một plugin cũ chỉ implements TextService vẫn dùng chức năng cơ bản. Một plugin mới implements BatchTextService có nghĩa vụ cung cấp applyBatch(...).

Khi host tìm provider, phải kiểm tra khả năng một cách tường minh, ví dụ:

~~~java
// Mã tích hợp: giả định provider là TextService đã được tạo.
if (provider instanceof BatchTextService batch) {
    var outputs = batch.applyBatch(java.util.List.of("a", "b"));
    // Xử lý kết quả batch theo contract.
}
~~~

Điều kiện ở đây dùng type identity của BatchTextService. Nếu plugin và host dùng hai bản API do những ClassLoader khác nhau định nghĩa, ngay cả cùng tên đầy đủ cũng **không nhất thiết là cùng kiểu**; phải chia sẻ API ổn định ở loader chung. Với SPI có registry riêng, host có thể tách service type cũ/mới và discovery theo version.

**Cách C — interface version mới hoặc adapter:** khi semantics cơ bản thay đổi (kiểu dữ liệu, error model, đồng bộ/bất đồng bộ, bảo mật), hãy tạo V2 contract riêng và adapter có kiểm thử. Đừng ép mọi plugin phải nhận một default no-op nhưng lại quảng cáo version V2 đã đầy đủ.

**Cách D — thêm abstract method:** có thể giữ binary compatibility theo JLS đối với file .class cũ, nhưng source provider cũ thường **không biên dịch lại được** nếu không cài đặt method; và nếu host gọi abstract method mới trên provider cũ chưa có implementation, có thể gặp **AbstractMethodError**. Không nhầm binary compatibility của việc "thêm abstract declaration" với tính khả dụng thực tế của plugin.

## 9. Những thay đổi khác cũng ảnh hưởng hợp đồng dù không liên quan default

| Thay đổi | Nguy cơ | Cách quản lý |
| --- | --- | --- |
| Thêm default method | Xung đột signature hoặc thay đổi semantics khi provider không override | Dùng tên ít va chạm, behavior bảo thủ, matrix test |
| Thêm abstract method | Provider cũ thiếu implementation lúc compile/invoke | Extension interface hoặc adapter/version mới |
| Xóa/đổi tên method | Caller cũ có thể gặp NoSuchMethodError | Giữ wrapper/deprecation, migration theo giai đoạn |
| Đổi tham số hoặc kiểu trả về | Thay JVM descriptor, overload/override có thể thay đổi | Xây method mới, duy trì method cũ qua adapter |
| Đổi instance thành static hoặc ngược lại | Có thể gây IncompatibleClassChangeError | Không đổi bản chất method trong API ổn định |
| Đổi checked exception được khai báo | Ảnh hưởng source compatibility, dù JVM không dùng throws giống descriptor | Xác định migration, test compile client |
| Đổi semantics mặc định | Plugin cũ chạy nhưng hành vi nghiệp vụ sai | Contract tests trên phiên bản cũ |
| Thêm method trùng Object như toString dưới dạng default | Java không cho phép khai báo default đó | Dùng tên helper hoặc override trong class |
| Thêm method có erasure/return mâu thuẫn | Lỗi compile, bridge/generic incompatibility | Kiểm thử generic subtyping và bytecode descriptor |
| Đưa thêm một bản API vào plugin JAR | Class identity khác nếu loader khác nhau | API chung do host/parent loader cung cấp |
| Đổi Java target/runtime requirement | Plugin/host không dùng được trên JRE cũ | Công khai JDK baseline, build với --release phù hợp |

**Đừng kết luận một exception chỉ từ tên.** NoSuchMethodError thường gợi ý method reference không tìm thấy theo runtime ABI; AbstractMethodError thường gợi ý đã tìm được abstract contract nhưng implementation không có body phù hợp; IncompatibleClassChangeError có nhiều nguyên nhân, trong đó có conflict default và sai kỳ vọng static/instance. Cần giữ stack trace, kiểm tra API JAR runtime, class loader và source/bytecode versions trước khi quyết định sửa.

## 10. Các bước nâng cấp hợp đồng plugin an toàn

Một kế hoạch thực tế nên có thứ tự:

1. **Ghi rõ v1 contract:** tên đầy đủ interface, public methods, generic signatures, exception semantics, nullability, thread-safety, callback lifecycle và khả năng hỗ trợ. Lưu artifact API v1.
2. **Kiểm kê provider hiện có:** class nào implements thêm interface khác, có public method trùng tên mới không, dùng JVM/JDK phiên bản nào, class loader nào sở hữu API.
3. **Đánh giá method mới:** có fallback đúng nghiệp vụ không? Có thể chọn default false/no-op hợp lệ không? Cần extension interface riêng không?
4. **Thiết kế source-compatibility test:** biên dịch lại mã nguồn những provider đại diện bằng API v2; lỗi override/covariant returns/generic erasure phải được phát hiện sớm.
5. **Thiết kế binary-compatibility test:** giữ nguyên plugin-old.jar build bằng API v1, chạy dưới host v2. Đây là bước thiết yếu: chỉ rebuild mọi thứ cùng API v2 không đủ kiểm tra upgrade độc lập.
6. **Thử nhiều superinterface:** đưa các provider implements nhiều interface độc lập vào test, đặc biệt có cùng method name/signature; kiểm tra cả compile-time conflict và invocation-time failures.
7. **Thử ServiceLoader/runtime:** chỉ cung cấp một bản API ở đúng loader chung; kiểm tra descriptor, public constructor classpath, dependency và nạp provider thực tế.
8. **Thử hành vi mặc định:** plugin cũ không có capability mới phải được chọn/lọc đúng, tránh đi vào tính năng nó không hỗ trợ. Đánh giá các trường hợp null, input lạ, error handling và side effect.
9. **Đặt version policy:** phân biệt bản API chủ và capability optional; deprecate method cũ trước khi bỏ hẳn; công khai compatibility matrix và thời gian hỗ trợ.
10. **Quan sát và rollback:** log plugin ID, API version, loader, lỗi liên kết và capability negotiation; nếu upgrade xuất hiện collision, phải có khả năng quay lại artifact/API tương thích hoặc dùng adapter/version riêng.

Một repository có thể dùng Maven/Gradle để tự động hóa test trên nhiều JDK; nguyên tắc không đổi: **giữ lại binary của provider cũ** làm fixture. Test chỉ có source của provider mới không bắt được mọi lỗi runtime ở môi trường người dùng chưa nâng cấp plugin.

## 11. Phân biệt lỗi triển khai với lỗi tiến hóa API

Nếu một plugin không được ServiceLoader tìm thấy, đừng vội kết luận default method mới gây lỗi:

| Dấu hiệu | Nghi ngờ chính | Bước xác minh |
| --- | --- | --- |
| 0 provider | Không có hoặc sai tên META-INF/services, JAR không trên classpath/loader | jar --list, loader context, descriptor |
| ServiceConfigurationError khi iterate | Provider class sai, constructor không phù hợp, API identity khác hoặc lỗi khởi tạo | Stack trace/cause và tên provider |
| NoSuchMethodError khi host gọi method mới | API runtime cũ hoặc method bị xóa/đổi descriptor | javap trên API thực tế được nạp, version JAR |
| AbstractMethodError | Host gọi method abstract mà provider runtime thiếu implementation thích hợp | Đối chiếu method abstract/default trong API và provider binary |
| IncompatibleClassChangeError ở method default | Có thể có hai default không liên quan hoặc thay đổi static/instance | Đối chiếu superinterfaces và JLS method resolution |
| Lỗi javac khi rebuild plugin | Xung đột defaults, return type/generic/visibility hoặc abstract mới | Compile fixture provider với API v2 |
| Chạy được nhưng capability sai | Default có semantics chưa phù hợp với plugin cũ | Behavioral contract tests và opt-in |
| ClassCastException hoặc "not a subtype" | Host/plugin nạp bản interface qua ClassLoader khác | So sánh defining loader và nguồn API class |
| Method đúng nhưng hành vi kỳ lạ | Thay default body, vô tình override, dependency mismatch | Log implementation đang được chọn, test diff semantics |

Công cụ hữu ích:

~~~bash
jar --list --file dist/plugin-old.jar
javap -public -classpath dist/api-v1.jar demo.api.TextService
javap -public -classpath dist/api-v2.jar demo.api.TextService
javap -public -classpath dist/plugin-old.jar demo.plugin.UpperPlugin
~~~

Với lớp phức tạp, thêm javap -c -p để xem bytecode và bridge methods (nếu có). Nhưng phải đọc **JAR runtime thực sự được nạp**, không chỉ tệp ngẫu nhiên trên máy; thứ tự classpath, parent delegation và ModuleLayer có thể khiến Java chọn bản khác với bản người vận hành nghĩ đang dùng.

## 12. Bài tập và tiêu chí kiểm tra kiến thức

**Bài tập A — nâng cấp bảo thủ:** Trong lab spi-evolution, giữ nguyên plugin-old.jar và đổi default supportsAdvanced() từ false sang true. Host vẫn có thể chạy, nhưng giải thích vì sao kết quả advanced=true **không chứng minh provider cũ hỗ trợ được một thao tác mới**. Từ đó chọn hợp đồng phù hợp hơn.

**Bài tập B — override từ provider mới:** Viết plugin v2 override supportsAdvanced() trả true; build riêng nó với api-v2.jar và so sánh với plugin-old.jar. Đảm bảo không đưa hai descriptor trùng không chủ đích vào cùng JAR/classpath.

**Bài tập C — conflict source:** Bổ sung một interface độc lập có default supportsAdvanced() vào implements của provider; biên dịch lại với API v2. Sửa collision bằng override rõ ràng và đánh giá cả semantics của hai interface.

**Bài tập D — conflict binary:** Trong binary-clash, giữ nguyên Both.class/Run.class cũ, thay Right.class mới. Ghi nhận lỗi tại runtime, rồi rebuild Both với một override name() hợp lệ; so sánh compile-time và runtime behavior.

**Bài tập E — class wins:** Trong DefaultRulesDemo, thay ParentClass.label() thành một giá trị khác rồi chạy lại. Thấy được method class được dùng mặc dù Tagged có default.

**Bài tập F — abstract vs default:** Thêm một abstract method mới vào TextService v2, biên dịch lại plugin cũ và phân tích lỗi. Nếu muốn plugin cũ chạy khi host chưa cần capability mới, cân nhắc default bảo thủ, extension interface hoặc adapter.

**Bài tập G — class loader:** Cố tình đóng cả api-v1.jar trong plugin JAR và cho plugin loader tự định nghĩa interface thay vì chia sẻ API do host cung cấp. Phân tích vì sao hai type có cùng binary name vẫn có thể không gán kiểu được cho nhau. Chỉ làm trong lab cô lập.

**Tiêu chí hoàn thành:** bạn cần giải thích chính xác (1) vì sao default có thể giữ binary của provider cũ, (2) khi nào xung đột giữa hai default cần override, (3) cách class wins và most-specific interface hoạt động, (4) khác biệt source/binary/behavior compatibility, (5) ý nghĩa các lỗi NoSuchMethodError, AbstractMethodError, IncompatibleClassChangeError, (6) khi nào nên dùng extension interface thay default, và (7) vì sao test upgrade phải dùng plugin binary cũ thật sự.

## 13. Tài liệu tham khảo

- [Java Language Specification SE 17 — Chapter 9: Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html), đặc biệt §9.4 và §9.4.1.3 về default, overriding và signature conflicts.
- [Java Language Specification SE 17 — Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html), đặc biệt §13.5.4, §13.5.7 về tiến hóa interface và default method.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) về discovery/khởi tạo provider.
- [Java SE 17 — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html) về kiểm tra classfile và method declarations.

**Kết luận:** default method là công cụ nâng cấp SPI mạnh khi có **fallback đúng và bảo thủ**, nhưng không xóa được xung đột đa kế thừa hoặc rủi ro semantics. Hãy dùng override tường minh để giải quyết conflict, giữ một bản API chung ở runtime, kiểm tra cả source lẫn binary của plugin cũ, và chọn extension interface/version mới khi capability không có default hợp lệ.