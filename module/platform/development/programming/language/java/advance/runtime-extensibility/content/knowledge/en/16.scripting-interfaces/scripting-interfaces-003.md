# Ánh xạ hàm kịch bản sang interface Java và xử lý kết quả không hỗ trợ

Trong một ứng dụng Java có thể mở rộng lúc chạy, host thường biết trước **hợp đồng Java** (ví dụ hàm định dạng văn bản, tính giá, kiểm tra quy tắc), còn người phát triển plugin muốn viết phần triển khai bằng một **ngôn ngữ kịch bản**. Nếu host gọi tên hàm qua chuỗi ở mọi nơi, mã ứng dụng dễ sai tên, sai đối số và khó thay đổi. Java Scripting API (JSR 223, module java.scripting) cung cấp interface tùy chọn **javax.script.Invocable**, cho phép một số script engine **ánh xạ các hàm của script sang một Java interface**.

Phương thức chính là:

~~~java
<T> T Invocable.getInterface(Class<T> clasz)
<T> T Invocable.getInterface(Object thiz, Class<T> clasz)
~~~

Cả hai đều có thể trả về **null** khi không tạo được implementation phù hợp. Điều đó cần được xử lý như một **kết quả không hỗ trợ/không khả dụng của phép ánh xạ**, không phải tự động là lỗi cú pháp, không đồng nghĩa toàn bộ script engine đã hỏng, và tuyệt đối không được gọi phương thức qua tham chiếu null.

Bài học làm rõ hợp đồng này, sự khác biệt giữa hai overload, đường kiểm tra capability, lỗi khi gọi hàm, ví dụ Java 17 độc lập không cần thư viện bên ngoài và cách tích hợp an toàn vào một host plugin thực tế.

## 1. Vấn đề: từ hàm script động sang hợp đồng Java có kiểu

Giả sử host có interface Java:

~~~java
public interface Greeter {
    String greet(String name);
}
~~~

Một script theo cú pháp JavaScript có thể định nghĩa hàm top-level cùng tên:

~~~javascript
function greet(name) {
    return "Hello, " + name;
}
~~~

Host muốn viết mã Java như sau:

~~~java
Greeter greeter = /* lấy adapter do engine cung cấp */;
System.out.println(greeter.greet("Lan"));
~~~

Thay vì mỗi nơi dùng:

~~~java
Object value = invocable.invokeFunction("greet", "Lan");
~~~

**Điểm lợi** của adapter interface là host giao tiếp qua một hợp đồng Java đã công bố; chữ ký phương thức được kiểm tra trong mã host và client không phải tự quản lý tên hàm dạng chuỗi ở mỗi lời gọi. Tuy vậy, việc một interface Java biên dịch được **không bảo đảm script thực thi đúng**: tên hàm trong engine, số lượng đối số, khả năng chuyển đổi giá trị, lỗi script và vòng đời engine vẫn phải được kiểm tra ở runtime.

Quy trình khái quát:

~~~text
Host có interface Greeter
            |
            v
Tìm ScriptEngine bằng tên/ngôn ngữ
            |
         null? ----------------------> Không có engine
            |
            v
Kiểm tra engine instanceof Invocable
            |
         false? ---------------------> Engine không hỗ trợ Invocable
            |
            v
Đánh giá/nạp script để định nghĩa hàm
            |
      ScriptException? --------------> Script chưa thiết lập được trạng thái
            |
            v
Invocable.getInterface(Greeter.class)
            |
         null? ----------------------> Không ánh xạ được Greeter
            |
            v
Gọi Greeter.greet(...)
            |
      lỗi lúc gọi? ------------------> Lỗi thực thi/conversion, không phải null mapping
            |
            v
Nhận kết quả theo hợp đồng Java
~~~

**Chỉ gọi adapter khi đã xác nhận nó khác null.** Không gộp tất cả nhánh vào một catch Exception rồi kết luận “engine không hỗ trợ interface”, bởi rất nhiều lỗi nằm ở giai đoạn khác.

## 2. Những kiểu null và không hỗ trợ hoàn toàn khác nhau

| Thao tác | Kết quả/cơ chế | Ý nghĩa đúng |
| --- | --- | --- |
| ScriptEngineManager.getEngineByName("JavaScript") | Có thể **null** | Không tìm được engine đã đăng ký dưới tên ấy trong môi trường và class loader đang dùng |
| engine instanceof Invocable | Có thể **false** | Engine tồn tại, nhưng không cung cấp khả năng gọi/ánh xạ thông qua Invocable |
| invocable.getInterface(Greeter.class) | Có thể **null** | Không tạo được adapter interface từ các hàm top-level mà engine hiện có |
| invocable.getInterface(scriptObject, Greeter.class) | Có thể **null** | Không tạo được adapter từ các phương thức của script object đã chọn |
| engine.eval(script) | Có thể trả về một giá trị **null** | Script đã được đánh giá; null này có thể là **giá trị của biểu thức**, không tự nói rằng interface mapping không hỗ trợ |
| greeter.greet("Lan") | Có thể trả về **null** | Hàm có thể hợp lệ nhưng giá trị trả về là null; phải xử lý theo hợp đồng nghiệp vụ |
| invocable.invokeFunction("unknown") | Có thể ném **NoSuchMethodException** | Không tìm được function phù hợp với tên/đối số khi gọi trực tiếp |
| engine.eval(script) hoặc invokeFunction(...) | Có thể ném **ScriptException** | Có lỗi khi đánh giá/chạy script; không nên biến thành kết quả “không hỗ trợ” mặc định |

Từng lớp có một phản ứng phù hợp: **thiếu engine**, **thiếu capability**, **không ánh xạ được interface**, **script lỗi**, **lỗi gọi method**, **giá trị business trả về null**. Đây là cơ sở để thiết kế status/telemetry chính xác.

Trong Java 17, module **java.scripting** vẫn cung cấp các interface javax.script. Tuy nhiên **Nashorn JavaScript engine đã bị loại khỏi JDK từ Java 15**. Vì vậy:

~~~java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
~~~

có thể trả null trên JDK 17 không cài thêm JavaScript engine. Không giả định “Java 17 có JavaScript engine mặc định”, không dùng tiếp engine.eval khi nó là null. Nếu muốn hỗ trợ JavaScript, phải cung cấp một implementation phù hợp (chẳng hạn ScriptEngine adapter của một thư viện JavaScript hiện đại) và kiểm tra phiên bản/khả năng thực tế của nó.

## 3. getInterface(Class<T>): ánh xạ hàm top-level

Hợp đồng của **Invocable.getInterface(Class<T> clasz)**:

- Đối số clasz là một đối tượng **Class đại diện cho Java interface**.
- Engine tìm các **hàm của script đã được đánh giá/biên dịch trong interpreter**, phù hợp với các method của interface.
- Nếu tạo được adapter, kết quả có kiểu Java **T**; host gọi các method của T như với implementation Java thông thường.
- Nếu không thể tạo được interface được yêu cầu, API cho phép trả về **null**.
- Nếu đối số **null** hoặc **không phải interface**, phương thức có hợp đồng ném **IllegalArgumentException**.

Ví dụ sử dụng thực tế, giả định đã có đối tượng engine hợp lệ hỗ trợ Invocable:

~~~java
// Snippet đặt trong method đang có ScriptEngine engine và Greeter.
engine.eval("function greet(name) { return 'Hello, ' + name; }");

Invocable invocable = (Invocable) engine;
Greeter greeter = invocable.getInterface(Greeter.class);

if (greeter == null) {
    System.out.println("Greeter mapping unsupported");
} else {
    System.out.println(greeter.greet("Lan"));
}
~~~

**Đây là đoạn tích hợp, không phải chương trình Java đứng riêng.** Phép cast chỉ hợp lệ sau khi kiểm tra engine instanceof Invocable; đoạn đầy đủ bên dưới thực hiện kiểm tra đó. Khả năng hỗ trợ JavaScript và quy tắc chuyển đổi Java/String do implementation của engine quyết định.

### Khi nào trả về null?

Các tình huống cần điều tra:

1. Script **chưa được eval/execute** nên engine chưa có hàm greet.
2. Hàm trong script có tên khác, được khai báo trong object hoặc scope khác thay vì top-level.
3. Interface có thêm method mà script không có hàm tương ứng.
4. Engine không hỗ trợ tạo interface với kiểu/đặc điểm phương thức được yêu cầu, hoặc implementation giới hạn chức năng này.
5. State của engine/script đã thay đổi, hoặc adapter được tìm từ engine/context không chứa các hàm mong đợi.

**Không dựa vào một suy luận duy nhất** như “không có đúng số hàm thì chắc chắn null”. API định nghĩa kết quả null cho trường hợp interface không khả dụng, còn chi tiết matching, overload, conversion và tạo proxy có thể phụ thuộc engine. Với một implementation cụ thể, phải test hợp đồng cần dùng.

### Interface Java nên thiết kế thế nào?

Dùng tên method rõ ràng, chữ ký đơn giản, số method vừa đủ, dữ liệu có thể truyền qua ranh giới Java/script và kết quả được kiểm tra ở host. Không xem Java annotation, overload, generic type parameter hoặc default method tự động tạo ra logic tương đương trong script. Với những trường hợp này, cần kiểm tra hỗ trợ engine cụ thể.

Một **functional interface** có duy nhất một abstract method thường là điểm bắt đầu dễ kiểm chứng, nhưng API **không giới hạn** getInterface chỉ nhận functional interface: một interface nhiều method vẫn có thể được hỗ trợ nếu script engine cung cấp mapping phù hợp.

## 4. getInterface(Object thiz, Class<T>): ánh xạ method trên script object

Một số script engine cho phép script tạo object chứa method. Khi đó phương thức:

~~~java
<T> T getInterface(Object thiz, Class<T> clasz)
~~~

yêu cầu **thiz** là một **đối tượng script có ý nghĩa đối với engine**, không phải bất kỳ Object Java ngẫu nhiên nào. Java API mô tả việc ánh xạ method trên script object; implementation có thể gọi tương đương **invokeMethod(thiz, methodName, args)**.

Ví dụ theo cú pháp JavaScript, chỉ dùng khi engine hỗ trợ tạo và trả về object từ biểu thức:

~~~java
// Snippet, giả định engine instanceof Invocable và Greeter đã khai báo.
Object scriptObject = engine.eval(
        "({ greet: function(name) { return 'Hi, ' + name; } })");

Greeter greeter = invocable.getInterface(
        scriptObject, Greeter.class);

if (greeter == null) {
    System.out.println("Object mapping unsupported");
} else {
    System.out.println(greeter.greet("Lan"));
}
~~~

Nếu engine có hỗ trợ đầy đủ cho kiểu object này, kết quả dự kiến là **Hi, Lan**. Đây là **ví dụ phụ thuộc implementation**; không khẳng định mọi JSR 223 engine hiểu cú pháp JavaScript hay hỗ trợ object-to-interface.

**Khi nào nên dùng overload nào?**

| Nhu cầu | Overload ưu tiên |
| --- | --- |
| Script định nghĩa các hàm ở top-level trong engine đã eval | getInterface(Greeter.class) |
| Script tạo một instance/object có các method | getInterface(scriptObject, Greeter.class) |
| Muốn gọi một hàm cụ thể, không nhất thiết có interface | invokeFunction("name", args...) |
| Muốn gọi một method cụ thể trên script object | invokeMethod(scriptObject, "name", args...) |

Hợp đồng **IllegalArgumentException** của overload hai tham số áp dụng khi **clasz null/không phải interface**, hoặc **thiz null/không đại diện cho script object hợp lệ**. Không truyền null để biểu diễn “hàm top-level”: hãy dùng overload một tham số.

Nếu engine tạo object cho mỗi lần eval, đừng dùng nhầm object của engine hoặc context khác. Script object thường gắn với vòng đời, state và runtime của engine đã tạo ra nó; việc lưu vào cache xuyên phiên reload có thể làm hỏng adapter hoặc giữ tham chiếu bộ nhớ lâu hơn dự tính.

## 5. Mẫu tích hợp thực tế: kiểm tra capability theo đúng thứ tự

Một host có thể viết một phương thức dùng lại cho interface Java cần triển khai bởi script:

~~~java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptException;
import java.util.Optional;

public final class ScriptAdapters {
    private ScriptAdapters() {
    }

    public static <T> Optional<T> mapTopLevel(
            ScriptEngine engine, String source, Class<T> api)
            throws ScriptException {

        if (engine == null) {
            return Optional.empty();
        }
        if (!(engine instanceof Invocable invocable)) {
            return Optional.empty();
        }
        engine.eval(source);
        return Optional.ofNullable(invocable.getInterface(api));
    }
}
~~~

**Đây là một Java class có thể biên dịch độc lập**, nhưng chưa có main và cần được gọi từ host với engine/source/API đúng. Mẫu chỉ cho thấy cách kiểm tra và ánh xạ, chưa phân biệt ba nguyên nhân unavailable trong kiểu kết quả: ở production nên dùng kết quả giàu thông tin hơn. **Optional.empty() không phải lỗi compile script**; ScriptException được giữ riêng. Và nếu api sai loại, IllegalArgumentException vẫn phải được xử lý như lỗi của caller, không đổi thành unsupported.

Nếu việc thiếu mapping là **tính năng tùy chọn**, host có thể từ chối đăng ký plugin đó với trạng thái UNSUPPORTED. Nếu interface là hợp đồng **bắt buộc**, host có thể báo lỗi cấu hình plugin và fail activation. Quyết định này thuộc về chính sách ứng dụng, không do getInterface tự đặt ra.

### Không ép cast trước khi kiểm tra

~~~java
// SAI: engine có thể null hoặc không implement Invocable.
Invocable invocable = (Invocable) engine;
Greeter greeter = invocable.getInterface(Greeter.class);
greeter.greet("Lan");
~~~

Đoạn sai có thể gặp NullPointerException, ClassCastException hoặc dùng adapter null. Trình tự an toàn là: **engine non-null → instanceof Invocable → eval script → getInterface non-null → invoke**.

### Phân biệt lỗi của phương thức getInterface và lời gọi adapter

- **getInterface trả null:** không có adapter phù hợp. Host chưa chạy business method.
- **getInterface nhận tham số sai:** IllegalArgumentException là lỗi gọi API.
- **Gọi method trên adapter:** có thể thực thi code script và xảy ra lỗi tại thời điểm invocation, kể cả khi adapter được tạo thành công.
- **Giá trị trả về không chuyển được về kiểu Java** hoặc có sự kiện script runtime: engine có thể bọc/đẩy exception theo quy tắc riêng; không giả định mọi lỗi đều xuất hiện dưới dạng checked ScriptException trực tiếp ở một Java interface vốn không khai báo throws.

Vì vậy, biên giới chạy plugin nên log **giai đoạn**, **engine/provider**, **interface name**, **script version**, nhưng không lộ source hoặc dữ liệu nhạy cảm trong error message gửi công khai.

## 6. Ví dụ Java 17 độc lập: kiểm thử mapping null và một engine thật nếu có

Trên JDK 17 không có JavaScript engine mặc định, một ví dụ chỉ dựa vào new ScriptEngineManager().getEngineByName("JavaScript") sẽ không chắc chắn chạy được phần mapping. Để **chạy được trên JDK 17 thuần**, chương trình dưới đây có hai nhánh:

- **contract**: một test double chỉ implement **Invocable**, không phải ScriptEngine thật, mô phỏng việc hàm chưa có, vừa được công bố, interface thiếu method và gọi tên hàm không tồn tại. Nhánh này luôn có output xác định, phù hợp kiểm thử xử lý null của host.
- **engine**: tìm ScriptEngine có tên JavaScript thực sự trong runtime, kiểm tra capability, eval một hàm và thử lấy Java interface. Nhánh này phụ thuộc engine được cài/khai báo, không giả định JDK 17 có sẵn.

Test double giúp kiểm chứng **quyết định của mã Java**; nó **không chạy JavaScript**, không chứng minh đặc tính của một engine bên thứ ba. Phần engine thật là bước integration test riêng.

### Tệp ScriptBridgeDemo.java

~~~java
import java.lang.reflect.Proxy;
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;
import javax.script.ScriptException;

public final class ScriptBridgeDemo {
    public interface Greeter {
        String greet(String name);
    }

    public interface Missing {
        String absent(String name);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println("usage: contract|engine");
            return;
        }
        if ("contract".equals(args[0])) {
            contract();
        } else if ("engine".equals(args[0])) {
            realEngine();
        } else {
            System.out.println("usage: contract|engine");
        }
    }

    private static void contract() throws Exception {
        ToyInvocable invocable = new ToyInvocable();

        // Chưa có hàm trong test double.
        System.out.println(
                "before=" + state(invocable.getInterface(Greeter.class)));

        // Mô phỏng việc script đã định nghĩa hàm greet.
        invocable.defineGreet();
        Greeter greeter = invocable.getInterface(Greeter.class);

        System.out.println("after=" + (
                greeter == null ? "unsupported" : greeter.greet("Lan")));

        // Interface này yêu cầu hàm absent, test double không có.
        System.out.println(
                "missing=" + state(invocable.getInterface(Missing.class)));

        try {
            invocable.invokeFunction("absent", "Lan");
        } catch (NoSuchMethodException e) {
            System.out.println("direct=NoSuchMethodException");
        }
    }

    private static String state(Object value) {
        return value == null ? "unsupported" : "supported";
    }

    private static void realEngine() {
        ScriptEngine engine =
                new ScriptEngineManager().getEngineByName("JavaScript");

        if (engine == null) {
            System.out.println("engine=unavailable");
            return;
        }
        if (!(engine instanceof Invocable invocable)) {
            System.out.println("engine=not-invocable");
            return;
        }

        try {
            engine.eval(
                    "function greet(name) { return 'Hello, ' + name; }");

            Greeter greeter =
                    invocable.getInterface(Greeter.class);

            if (greeter == null) {
                System.out.println("interface=unsupported");
                return;
            }

            System.out.println("value=" + greeter.greet("Lan"));
        } catch (ScriptException e) {
            System.out.println("script=failed");
        } catch (RuntimeException e) {
            System.out.println("invocation=failed");
        }
    }

    // Test double của Invocable, KHÔNG phải JavaScript engine.
    private static final class ToyInvocable implements Invocable {
        private boolean ready;

        void defineGreet() {
            ready = true;
        }

        @Override
        public <T> T getInterface(Class<T> type) {
            if (type == null || !type.isInterface()) {
                throw new IllegalArgumentException(
                        "Expected an interface");
            }
            if (!ready || type != Greeter.class) {
                return null;
            }

            Object instance = Proxy.newProxyInstance(
                    type.getClassLoader(),
                    new Class<?>[] { type },
                    (proxy, method, args) -> {
                        if (method.getDeclaringClass() == Object.class) {
                            return switch (method.getName()) {
                                case "toString" -> "ToyGreeter";
                                case "hashCode" ->
                                        System.identityHashCode(proxy);
                                case "equals" -> proxy == args[0];
                                default ->
                                        throw new UnsupportedOperationException();
                            };
                        }

                        return invokeFunction(
                                method.getName(),
                                args == null ? new Object[0] : args);
                    });

            return type.cast(instance);
        }

        @Override
        public <T> T getInterface(Object thiz, Class<T> type) {
            if (thiz == null || type == null || !type.isInterface()) {
                throw new IllegalArgumentException(
                        "Invalid script object or interface");
            }

            // Test double không hỗ trợ script-object mapping.
            return null;
        }

        @Override
        public Object invokeFunction(String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            if (name == null) {
                throw new NullPointerException("name");
            }
            if (!ready || !"greet".equals(name)) {
                throw new NoSuchMethodException(name);
            }
            return "Hello, " + args[0];
        }

        @Override
        public Object invokeMethod(
                Object thiz, String name, Object... args)
                throws ScriptException, NoSuchMethodException {

            if (thiz == null) {
                throw new IllegalArgumentException("thiz");
            }
            if (name == null) {
                throw new NullPointerException("name");
            }
            throw new NoSuchMethodException(name);
        }
    }
}
~~~

### Biên dịch và chạy

Từ thư mục chứa file trên, dùng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 ScriptBridgeDemo.java
java ScriptBridgeDemo contract
~~~

**Stdout chính xác của chế độ contract:**

~~~text
before=unsupported
after=Hello, Lan
missing=unsupported
direct=NoSuchMethodException
~~~

Giải thích:

1. Trước defineGreet, getInterface(Greeter.class) trả null.
2. Sau defineGreet, test double dùng Java dynamic proxy để trả implementation Greeter; lời gọi greet được chuyển thành invokeFunction trong test double.
3. Interface Missing yêu cầu method absent không được mô phỏng; getInterface(Missing.class) trả null.
4. Khi gọi trực tiếp invokeFunction("absent", "Lan"), test double ném NoSuchMethodException thay vì trả null. Đây là một quy tắc khác với getInterface.

Tiếp tục:

~~~bash
java ScriptBridgeDemo engine
~~~

**Trên JDK 17 thông thường không cài thêm JavaScript ScriptEngine**, stdout dự kiến:

~~~text
engine=unavailable
~~~

Nếu hệ thống đã cài engine JavaScript, output **phụ thuộc capability**: có thể là engine=not-invocable, interface=unsupported, script=failed, invocation=failed, hoặc (nếu engine chấp nhận script và mapping) là:

~~~text
value=Hello, Lan
~~~

Không gộp các output trên thành kết quả một lần chạy. Đừng sửa JDK hoặc bí mật thêm dependency chỉ để ép nhánh engine thành công; trong dự án thật, dependency engine phải được quản lý và kiểm thử theo cùng phiên bản ở development, CI và production.

### Vì sao ví dụ dùng dynamic proxy?

ToyInvocable là **mock** để mô phỏng hợp đồng của Invocable, không phải một hệ biên dịch script. Nó kiểm soát được trạng thái hỗ trợ/null và giúp chạy kiểm thử mà không phụ thuộc engine của máy. Dùng Proxy trong test double cho thấy một adapter Java có thể thực thi lời gọi giao diện bằng cách chuyển sang hàm động; **đây không phải cam kết engine thật sử dụng đúng java.lang.reflect.Proxy trong triển khai nội bộ**.

Phần realEngine là code tích hợp thực tế có kiểm tra engine hiện hữu, hỗ trợ Invocable và adapter non-null. Nó có thể biên dịch trên JDK 17 vì toàn bộ javax.script API nằm trong java.scripting, dù môi trường chạy không có JavaScript engine.

## 7. Xử lý kết quả không hỗ trợ trong thiết kế host/plugin

Một host lớn nên định nghĩa kết quả có kiểu thay cho một null không rõ nguyên nhân. Ví dụ:

~~~java
enum ScriptBindingStatus {
    ENGINE_UNAVAILABLE,
    ENGINE_NOT_INVOCABLE,
    SCRIPT_EVALUATION_FAILED,
    INTERFACE_UNSUPPORTED,
    READY,
    INVOCATION_FAILED
}
~~~

Đây là enum minh họa để tích hợp vào một application service; không phải chương trình chạy riêng. Tách trạng thái READY (adapter được tạo) khỏi các lỗi trong lần gọi method tương lai.

Bảng chính sách ví dụ:

| Trạng thái | Cách xử lý plugin |
| --- | --- |
| ENGINE_UNAVAILABLE | Nếu tính năng script tùy chọn: disable plugin và báo rõ thiếu engine; nếu bắt buộc: fail startup/activation |
| ENGINE_NOT_INVOCABLE | Không dùng getInterface; từ chối plugin dựa trên interface hoặc chọn một adapter được hỗ trợ khác theo cấu hình |
| SCRIPT_EVALUATION_FAILED | Thất bại thực sự khi nạp script; cung cấp diagnostics có kiểm soát, không đổi thành “không hỗ trợ” |
| INTERFACE_UNSUPPORTED | Không kích hoạt adapter, giữ an toàn cho host, báo tên method/interface còn thiếu nếu engine cho phép xác định |
| READY | Lưu adapter cùng engine/context đang sống, sử dụng qua contract đã kiểm tra |
| INVOCATION_FAILED | Ghi lỗi tại lần gọi, áp dụng timeout/circuit breaker/rollback phù hợp, không coi lần đăng ký adapter trước đó là sai mặc định |

**Không cố định một hành vi cho tất cả plugin:** Với interface tùy chọn như HealthCheck, thiếu interface có thể chỉ làm tắt tính năng kiểm tra sức khỏe riêng. Với interface bắt buộc như PaymentRule, thiếu interface phải từ chối toàn bộ plugin. Quyết định nghiệp vụ được xác định từ metadata/hợp đồng của host, không được suy ra chỉ từ null.

### Phân biệt null hợp đồng và null dữ liệu

Giả sử adapter Greeter được tạo thành công, nhưng một hàm script trả null theo điều kiện nghiệp vụ. Lúc này:

~~~java
Greeter greeter = invocable.getInterface(Greeter.class);

if (greeter == null) {
    // Không có adapter phù hợp: chưa thực hiện greet.
} else {
    String result = greeter.greet("Lan");
    if (result == null) {
        // Adapter tồn tại, nhưng business method trả null.
    }
}
~~~

Đây là snippet chẩn đoán trong một method đã có invocable và Greeter; không phải chương trình độc lập. Hai lần kiểm tra null thể hiện **hai tầng ý nghĩa khác nhau**. Không nên dùng một kết quả null chung cho cả hai trường hợp khi API cần phân biệt.

### Bẫy Optional và exception

Optional.ofNullable(invocable.getInterface(...)) hữu ích khi host chỉ quan tâm có adapter hay không. Nhưng nếu ứng dụng cần phân tích nguyên nhân, hãy trả một kết quả riêng có status, diagnostic và payload adapter tùy chọn. Optional không mang được nguyên nhân thiếu engine hay script lỗi.

Cũng không nên bắt mọi RuntimeException rồi quy là INTERFACE_UNSUPPORTED. Ví dụ lỗi chuyển đổi kiểu trả về hoặc runtime exception do script đang chạy là **INVOCATION_FAILED**, còn IllegalArgumentException do truyền Class không phải interface là **lỗi lập trình của host**.

## 8. Về tên method, tham số và kiểu trả về

Việc ánh xạ dựa trên API mang kiểu **không biến một scripting language động thành Java compiler cho script**. Một số khác biệt cần kiểm tra khi tích hợp:

- **Tên**: method của interface và tên hàm/thuộc tính script phải được engine nhận diện là tương ứng. Viết sai chữ hoa/chữ thường có thể dẫn tới không ánh xạ được.
- **Số lượng tham số**: Java method khai báo chữ ký; engine có thể dùng quy tắc riêng cho thiếu/thừa đối số hoặc variadic arguments. Không suy đoán từ một ngôn ngữ khác.
- **Overload**: Java cho phép nhiều method cùng tên khác parameter types, trong khi nhiều ngôn ngữ script coi tên hàm như một key. Tránh overload phức tạp trừ khi engine chứng minh có chính sách matching rõ ràng.
- **Kiểu tham số**: Integer, String, List, Map, object host hoặc giá trị null có thể được chuyển đổi thành đối tượng script theo quy tắc implementation. Dùng DTO đơn giản và hợp đồng phiên bản hóa thay vì truyền object nội bộ không kiểm soát.
- **Kiểu trả về**: giá trị script có thể không chuyển được về kiểu Java đã khai báo. Một proxy/adapter có thể báo lỗi lúc invocation dù getInterface đã trả khác null.
- **Giá trị nguyên thủy**: một method Java trả int/boolean không thể nhận null để unbox an toàn; cần kiểm thử kiểu/giới hạn số và xử lý lỗi của engine.
- **Checked exceptions**: method Java của interface không khai báo ScriptException mặc định. Engine có thể bọc lỗi script thành unchecked exception khi chuyển qua adapter; kiểm tra hợp đồng thực tế thay vì bắt ScriptException ở nơi compiler không cho phép.
- **Default, static và Object methods**: không giả định adapter script hỗ trợ mọi đặc tính interface như một Java class viết tay. Kiểm tra ít nhất những method thực sự dùng trong runtime.

Lợi ích chính của interface là **contract tĩnh cho host**, còn khả năng thực thi script đúng phải được bảo đảm bằng integration tests cho engine cụ thể.

## 9. Module java.scripting, class loader và lifecycle của engine

Nếu host là **explicit JPMS module** và trực tiếp dùng javax.script, descriptor tối thiểu thường gồm:

~~~java
module demo.host.scripting {
    requires java.scripting;
}
~~~

Đây là ví dụ descriptor; các module khác còn phụ thuộc mã host thực tế. requires java.scripting cấp quyền truy cập API javax.script, **không tự cài một script engine**. Engine thật phải có trong ứng dụng/module path/classpath và được đăng ký theo cơ chế tương ứng để ScriptEngineManager khám phá được.

### Khám phá engine phụ thuộc môi trường chạy

ScriptEngineManager dùng cơ chế service discovery đối với ScriptEngineFactory, có liên hệ với **thread context class loader** ở các constructor phù hợp. Plugin JAR có engine nhưng không nhìn thấy được từ loader/module layer mà manager sử dụng vẫn có thể dẫn đến getEngineByName trả null. Trong hệ plugin động, cần xác định loader/layer của **factory** và **engine**, không chỉ nhìn vào JAR trong thư mục plugins.

Nếu script engine tồn tại trong ModuleLayer riêng, host cần thiết kế cách khám phá/khởi tạo qua ranh giới module thích hợp; không chắc manager mặc định quét được tất cả module layer tự tạo. Vì vậy log cả tên engine được yêu cầu, danh tính loader và nguồn provider khi chẩn đoán, thay vì khẳng định tên engine sai ngay lập tức.

### Vòng đời và thread safety

1. Tạo engine theo scope phù hợp (plugin instance, tenant, session hoặc request), không tự gộp toàn hệ thống vào một ScriptEngine chung.
2. Eval script trước khi lấy adapter; lưu adapter cùng **engine và script object/context cần thiết** cho suốt thời gian sử dụng.
3. Khi cập nhật script, xác định rõ reload làm thay đổi trạng thái trong engine hay tạo engine/context mới; adapter cũ có thể còn ràng buộc với state cũ.
4. **Không mặc định ScriptEngine an toàn để nhiều thread gọi cùng lúc.** Xem ScriptEngineFactory.getParameter("THREADING") và tài liệu engine; tham số này chỉ là metadata và cần được xác minh bằng kiểm thử/contract của implementation cụ thể.
5. Đặt giới hạn số lượng engine, thời gian chạy, dung lượng dữ liệu và kích thước state; dọn tài nguyên theo API/lifecycle engine (nếu implementation có close hoặc context API riêng).
6. Khi dừng plugin, ngắt việc nhận invocation mới và chờ tác vụ đang chạy theo chính sách; không giữ khóa registry trong lúc chờ script có thể callback vào host.

**Không giữ adapter đã map như một Java object vĩnh viễn** nếu engine/module layer mà nó phụ thuộc đã được đóng/unload. Điều đó có thể làm lỗi lời gọi sau hoặc giữ class loader/plugin class không được thu gom.

## 10. Bảo mật khi script trở thành một implementation của interface

Ánh xạ sang interface giúp thu hẹp **bề mặt giao tiếp của host**, nhưng **không làm script tự động an toàn**. Script có thể chạy code trong quá trình engine.eval và khi gọi method qua adapter. Tùy engine, nó có thể truy cập API Java, reflection, file, network, CPU/RAM và callback host.

Các biện pháp cần cân nhắc:

- Chỉ chạy script tin cậy trong cùng JVM nếu môi trường và quyền của engine cho phép. Với script không tin cậy, cân nhắc **process/container riêng**, chính sách hệ điều hành, giới hạn tài nguyên và kênh RPC có kiểm soát; adapter trong JVM không phải sandbox.
- Không truyền tùy ý toàn bộ đối tượng host, database handle, registry hoặc secret vào script bindings. Chỉ cấp các dịch vụ/hợp đồng tối thiểu.
- Giới hạn timeout, số invocation, kích thước tham số/giá trị trả về, số plugin đang hoạt động và mức độ logging. **Invocable.getInterface không có API timeout chung**; timeout thường phải đặt ở tầng worker/engine cụ thể.
- Cô lập state giữa các tenant và plugin; tránh dùng nhầm bindings hoặc adapter từ một engine của tenant khác.
- Kiểm tra script provenance, version và chính sách cập nhật; việc cùng tên interface không bảo đảm script mới có hành vi tương thích.
- Khi script lỗi, log thông tin giúp chẩn đoán mà không tiết lộ source nhạy cảm hoặc dữ liệu đầu vào cho người không có quyền xem.

Không chọn “trả null khi lỗi” để che giấu một exception từ script đã thực thi: thao tác đó khiến lỗi bảo mật/vận hành trông giống thiếu capability bình thường.

## 11. Chẩn đoán lỗi theo thứ tự

Khi host không tạo được adapter Greeter, hãy đi từ **discovery → capability → eval → mapping → invoke**.

| Triệu chứng | Khả năng đáng kiểm tra trước | Bước xác nhận |
| --- | --- | --- |
| engine == null | Thiếu ScriptEngineFactory/engine dependency hoặc manager không thấy provider | Liệt kê getEngineFactories; kiểm tra engine name, class loader và module layer |
| Engine có nhưng không instanceof Invocable | Engine implementation không có optional capability | Kiểm tra tài liệu/kiểu runtime, chọn adapter khác hoặc báo unsupported |
| getInterface trả null | Thiếu function/method phù hợp, sai scope hoặc engine không hỗ trợ mapping này | Kiểm tra script đã eval, interface methods, tên/scope, engine docs |
| getInterface(thiz, interface) ném IllegalArgumentException | thiz null/không phải script object hợp lệ hoặc clasz không phải interface | Xác định object được trả từ engine tương ứng và class hợp lệ |
| Lỗi lúc eval | Script source lỗi hoặc thiếu context/dependency | Giữ ScriptException/diagnostics, không đổi thành null mapping |
| getInterface khác null nhưng gọi method lỗi | Runtime exception trong script, conversion mismatch, engine state đã mất | Log invocation và cause theo engine, test đối số/return type |
| invokeFunction ném NoSuchMethodException | Tên hoặc chữ ký hàm gọi trực tiếp không tồn tại/không tương thích | Kiểm tra function name, args, scope đã eval |
| Chạy thử được, production không có engine | Runtime packaging/module/class loader khác development | Kiểm tra artifact và engine provider tại production |
| Lâu lâu lỗi khi nhiều request dùng chung adapter | Engine/context không thread-safe, state race hoặc lifecycle reload | Đối chiếu THREADING contract và test concurrent usage |

Ví dụ chẩn đoán engine list (snippet có thể đặt trong Java main hoặc method):

~~~java
ScriptEngineManager manager = new ScriptEngineManager();

for (var factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName()
            + " -> " + factory.getNames());
}
~~~

Nếu danh sách không chứa JavaScript engine thì getEngineByName("JavaScript") có thể null trên Java 17. Không dùng stdout cụ thể của đoạn trên làm điều kiện test; danh sách phụ thuộc những nhà cung cấp được cài trong runtime.

### Các lỗi dễ mắc

1. **Quên kiểm tra engine null** và gọi eval ngay trên null.
2. **Cast ScriptEngine sang Invocable mà không kiểm tra**, dẫn đến ClassCastException với engine không hỗ trợ.
3. **getInterface trả null nhưng vẫn gọi method**, dẫn đến NullPointerException.
4. **Nhầm kết quả null từ script function với null mapping**, khiến host báo sai lý do.
5. **Nhầm invokeFunction/NoSuchMethodException với getInterface/null**, dù đây là hai API và hai kiểu kết quả khác nhau.
6. **Dùng getInterface(thiz, type) với thiz null hoặc Java object sai loại**, dẫn đến IllegalArgumentException theo hợp đồng.
7. **Lấy adapter trước eval** hoặc lấy từ engine không có state hàm tương ứng.
8. **Nhầm function top-level với method trên script object**, chọn sai overload.
9. **Trông chờ Nashorn có sẵn trong Java 17**, dù đã bị loại khỏi JDK.
10. **Coi mọi engine có javax.script đều hỗ trợ mapping**, trong khi Invocable là optional.
11. **Tin rằng có adapter nghĩa là mọi lần gọi sẽ thành công**, bỏ qua conversion/lifecycle.
12. **Chia sẻ ScriptEngine/adapter giữa các thread hoặc tenant khi chưa kiểm chứng** tính an toàn và phạm vi state.

## 12. Ma trận kiểm thử cho host runtime extensibility

Nên có cả **unit test chính sách** (dùng test double Invocable) lẫn **integration test engine thật** (engine và version giống production).

1. **Không có engine:** manager trả null; host ghi ENGINE_UNAVAILABLE, không eval/cast.
2. **Engine không implement Invocable:** host ghi ENGINE_NOT_INVOCABLE, không ép cast.
3. **Invocable nhưng script chưa có function:** getInterface trả null; host ghi INTERFACE_UNSUPPORTED theo contract engine đang test.
4. **Function đã được eval và mapping hợp lệ:** adapter non-null, gọi method trả dữ liệu đúng kiểu.
5. **Interface thêm một method chưa được script hỗ trợ:** host phát hiện không mapping hoặc xử lý policy engine tương ứng.
6. **Object-based mapping:** kiểm tra getInterface(scriptObject, Interface.class) và trường hợp thiz không hợp lệ.
7. **Interface API sai:** truyền Class không phải interface/null, xác nhận lỗi input rõ ràng.
8. **Lỗi eval:** source sai, kiểm tra ScriptException và không ghi thành unsupported.
9. **Lỗi lúc invoke:** hàm script ném lỗi, mismatch kiểu trả về, state engine không còn; host gắn INVOCATION_FAILED.
10. **Một method hợp lệ trả null:** kiểm tra đây là null nghiệp vụ, khác adapter null.
11. **Concurrency và reload:** kiểm tra phạm vi engine, cập nhật script, cleanup và việc không giữ adapter của plugin đã dừng.
12. **Packaging Java 17:** kiểm tra với JDK thuần không có JS engine và với môi trường có engine đã cấu hình.

**Đừng cố ép integration test thành công trên JDK 17 thuần bằng cách giả định có JavaScript engine.** Test nhánh engine unavailable là kết quả hợp lệ. Test capability thực cần mang theo dependency cụ thể và thiết lập engine trong CI đúng như production.

## 13. Checklist thiết kế adapter script sang Java interface

- Có **Java interface** công khai, tên và kiểu method tối giản, ổn định phiên bản.
- Có **engine provider** đã cài đặt/được class loader phù hợp khám phá; xử lý khi manager trả null.
- Engine **thực sự implement Invocable**; kiểm tra trước khi gọi.
- Script **đã eval** trong đúng engine/context trước khi tạo adapter.
- Chọn đúng **getInterface(Class<T>)** cho function top-level hoặc **getInterface(thiz, Class<T>)** cho script-object methods.
- Đối tượng thiz đúng dạng **script object** do engine cung cấp; clasz là **interface Class**, không null.
- Kiểm tra **getInterface result non-null**, không suy ra một cách mù quáng từ việc eval thành công.
- Phân biệt **ENGINE_UNAVAILABLE, NOT_INVOCABLE, INTERFACE_UNSUPPORTED, SCRIPT_EVALUATION_FAILED, INVOCATION_FAILED**.
- Kiểm thử chuyển đổi Java/script cho **đối số, giá trị null, primitives, return type và exceptions**.
- Có quy tắc **engine/context/adapter lifecycle**, tránh cross-tenant/cross-thread state không kiểm soát.
- Xác định **mức độ tin cậy của script**, quyền cấp cho plugin và cơ chế cô lập nếu cần.
- Test cả trường hợp **thiếu JavaScript engine trên JDK 17** lẫn engine thực tế đã cài trong bản phân phối.

**Kết luận:** Interface Java là **ranh giới hợp đồng** cho host, còn ánh xạ từ script là một **capability tùy chọn** của engine. Luôn đi theo thứ tự: **tìm engine → kiểm tra Invocable → eval script → yêu cầu getInterface → kiểm tra null → gọi method và xử lý lỗi runtime**. Sự khác biệt giữa **không có engine**, **không hỗ trợ ánh xạ**, **lỗi script** và **method trả null** là cốt lõi để một hệ runtime extensibility có hành vi rõ ràng và dễ vận hành.

## Tài liệu tham khảo

- [Java SE 17 — javax.script.Invocable](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Invocable.html): hai overload getInterface, giá trị null, IllegalArgumentException, invokeFunction và invokeMethod.
- [Java SE 17 — ScriptEngineManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): tìm engine bằng tên, service discovery và factories.
- [Java SE 17 — ScriptEngine](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): hợp đồng eval và context.
- [JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): lý do không mặc định có Nashorn từ JDK 15.