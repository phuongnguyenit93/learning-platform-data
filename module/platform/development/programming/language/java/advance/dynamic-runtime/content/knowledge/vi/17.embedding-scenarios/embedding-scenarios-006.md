# 17.6 Kiểm tra khả năng `Invocable`, gọi hàm và ánh xạ sang interface

## 1. Bài toán: từ một script đã thực thi đến lời gọi Java có kiểu

Khi nhúng một ngôn ngữ kịch bản vào Java, `javax.script.ScriptEngine` thường được dùng để **đánh giá một đoạn script** qua `eval(...)`. Nhưng ứng dụng thực tế không chỉ muốn chạy cả đoạn script rồi nhận một kết quả chung. Nó thường cần:

- **Gọi lại một hàm** đã được script định nghĩa, theo tên và danh sách đối số.
- **Gọi method của một script object** đã được tạo ra trước đó.
- **Ánh xạ** những hàm/method đó sang một **interface Java**, để code ứng dụng gọi `calculator.add(2, 5)` thay vì lặp lại `invokeFunction("add", 2, 5)`.
- **Phát hiện đúng năng lực** của engine; không phải mọi `ScriptEngine` đều thực thi interface `Invocable`.
- **Báo lỗi đúng lớp** khi engine không tồn tại, không hỗ trợ gọi hàm, hàm không tồn tại, script ném lỗi hoặc kết quả không tương thích kiểu Java.

API chính của bài là **`javax.script.Invocable`** (JSR 223, module `java.scripting`). Đây là **giao diện tùy chọn** mà một số `ScriptEngine` implement để cho phép gọi các hàm/method **đã được thực thi/định nghĩa trước** trong môi trường của engine.

> **Quy tắc cốt lõi:** Có `ScriptEngine` không đồng nghĩa có `Invocable`. Cần kiểm tra `engine instanceof Invocable`; nếu đúng, **đánh giá/nạp script trước**, rồi mới gọi `invokeFunction`/`invokeMethod` hoặc lấy adapter bằng `getInterface`. Java 17+ **không còn Nashorn JavaScript engine tích hợp**, vì vậy không được mặc định `getEngineByName("JavaScript")` sẽ trả engine khác `null`.

Bài cung cấp một **ví dụ Java 17+ hoàn toàn độc lập, có thể biên dịch/chạy trên JDK chuẩn**. Để không phụ thuộc cài đặt JavaScript bên ngoài, ví dụ dùng một **engine nhỏ tự viết làm fixture giảng dạy**, implement `Invocable` và dùng JDK Proxy để minh họa ánh xạ interface. Fixture này **không phải** trình thông dịch JavaScript và **không** tự đăng ký với `ScriptEngineManager`. Một ví dụ riêng cho script JavaScript thật được ghi rõ là **có điều kiện** khi đã có nhà cung cấp JSR 223 tương thích.

## 2. Kiến trúc JSR 223 và vị trí của `Invocable`

Các kiểu trọng tâm nằm trong package `javax.script`:

| API | Trách nhiệm | Cần lưu ý |
| --- | --- | --- |
| `ScriptEngineManager` | Tìm các `ScriptEngineFactory` hiện có, tạo engine theo name/extension/MIME | Không tự cài thêm engine; trả `null` nếu không có provider phù hợp |
| `ScriptEngineFactory` | Mô tả tên, phiên bản, ngôn ngữ và cách tạo engine | Engine có thể có nhiều alias; cần xem provider cụ thể |
| `ScriptEngine` | `eval` code, quản lý `Bindings` và `ScriptContext` | Không bắt buộc hỗ trợ gọi hàm theo tên |
| `AbstractScriptEngine` | Lớp nền tiện ích cho người viết engine | **Không** tự implement `Invocable` |
| `Invocable` | `invokeFunction`, `invokeMethod`, hai overload `getInterface` | Tùy chọn; engine không implement thì không được ép kiểu |
| `Compilable` | Tùy chọn biên dịch script sang `CompiledScript` | **Độc lập** với `Invocable`; `Compilable` không thay thế `Invocable` |
| `Bindings` | Tập biến theo tên giữa Java và engine | Không mặc định mọi binding đều là script function |
| `ScriptException` | Lỗi đánh giá/gọi script | Phân biệt với `NoSuchMethodException` từ lookup hàm |

**Quy trình thường gặp:**

```text
ScriptEngineManager / provider đã đăng ký
              |
              v
      ScriptEngine engine
              |
       engine != null ?
          /        \
        no          yes
        |            |
   thông báo       engine.eval(source)
   thiếu engine           |
                          v
               engine instanceof Invocable ?
                       /          \
                     no            yes
                     |              |
             dùng eval hoặc         v
             engine khác     Invocable inv
                                 |
                 +---------------+---------------+
                 |               |               |
           invokeFunction    invokeMethod      getInterface
              hàm global     method của obj    Java typed view
```

**Phân biệt hai năng lực:** `ScriptEngine.eval("add(2, 5)")` có thể chạy được dù engine **không implement `Invocable`**, vì đó là cú pháp của ngôn ngữ script bên trong một chuỗi. `Invocable.invokeFunction("add", 2, 5)` là một API Java để gọi **hàm đã được chuẩn bị** mà không cần dựng lại một chuỗi expression. Không thể dựa vào việc `eval` có sẵn để ép engine thành `Invocable`.

### 2.1. `Invocable` không phải là `java.lang.reflect.Method`

Tên giống nhau nhưng cơ chế khác nhau:

- `Method.invoke(receiver, args...)` gọi **method Java** đã được khai báo trong class bytecode.
- `Invocable.invokeFunction(name, args...)` gọi **hàm script toàn cục** theo tên trong trạng thái của engine.
- `Invocable.invokeMethod(thiz, name, args...)` gọi **method thuộc một script object** mà engine biết.
- `Invocable.getInterface(...)` dựng adapter để Java gọi các method của **interface đã khai báo** và chuyển sang script.

`Invocable` **không biên dịch Java source**, không làm class Java có method mới, và không có quyền truy cập private Java members chỉ nhờ việc implement giao diện này.

## 3. Kiểm tra engine tồn tại và hỗ trợ `Invocable`

### 3.1. Luôn kiểm tra engine trước khi ép kiểu

Một đoạn an toàn về mặt luồng điều khiển:

```java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

ScriptEngineManager manager = new ScriptEngineManager();
ScriptEngine engine = manager.getEngineByName("JavaScript");

if (engine == null) {
    System.out.println("Chưa có JSR 223 JavaScript engine.");
} else if (!(engine instanceof Invocable inv)) {
    System.out.println("Engine tồn tại nhưng không hỗ trợ Invocable.");
} else {
    System.out.println("Có thể dùng Invocable với engine này.");
    // Tiếp tục eval script và gọi những hàm đã định nghĩa.
}
```

Đây là **trích đoạn Java**, không phải chương trình đầy đủ: cần đặt các statement trong một method/class. Mục đích là minh họa guard, không cam kết output giống nhau trên mọi JDK.

Java 17 vẫn cung cấp API `javax.script` nhưng **Nashorn được gỡ khỏi JDK từ Java 15** (JEP 372). Một JDK 17 sạch có thể không chứa engine nào mang alias `"JavaScript"`, nên `getEngineByName` có thể trả `null`. Nếu ứng dụng cần JavaScript, hãy bổ sung một engine/provider hỗ trợ JSR 223 có phiên bản tương thích, cấu hình dependencies và class loader/module path theo tài liệu provider.

**Đừng dùng:**

```java
// SAI nếu engine không tồn tại hoặc không hỗ trợ Invocable.
Invocable inv = (Invocable) new ScriptEngineManager()
        .getEngineByName("JavaScript");
Object result = inv.invokeFunction("add", 2, 5);
```

Trường hợp `getEngineByName` trả `null`, cast `null` thành `Invocable` vẫn cho kết quả `null`, rồi lời gọi `inv.invokeFunction` mới ném `NullPointerException`. Nếu engine tồn tại nhưng không implement `Invocable`, ép kiểu thất bại bằng `ClassCastException`. Cả hai đều tránh được bằng kiểm tra riêng như mẫu phía trên.

### 3.2. Pattern matching giúp giữ biến có kiểu đúng

Với Java 17:

```java
if (!(engine instanceof Invocable inv)) {
    throw new IllegalStateException("Engine không hỗ trợ gọi hàm script");
}
Object value = inv.invokeFunction("add", 2, 5);
```

Mẫu này là **trích đoạn** giả định `engine` đã được kiểm tra non-null và script có hàm `add`. Dùng `instanceof` guard **không** có nghĩa `add` chắc chắn tồn tại: nó chỉ xác nhận **khả năng của engine**.

### 3.3. Có thể tra cứu provider được cài đặt

Để điều tra engine availability:

```java
ScriptEngineManager manager = new ScriptEngineManager();
for (javax.script.ScriptEngineFactory factory : manager.getEngineFactories()) {
    System.out.println(factory.getEngineName() + ": " + factory.getNames());
}
```

Đây cũng là **trích đoạn**. Output phụ thuộc các `ScriptEngineFactory` được phát hiện trong môi trường, không có danh sách cố định của “Java 17”. Nếu không tìm thấy engine mong muốn, hãy kiểm tra provider JAR/module, service registration, class loader và các dependencies, không sửa tên engine một cách đoán mò.

## 4. `invokeFunction`: gọi hàm toàn cục đã được định nghĩa

Chữ ký:

```java
Object invokeFunction(String name, Object... args)
        throws ScriptException, NoSuchMethodException;
```

Một chương trình thường thực hiện:

1. Lấy `ScriptEngine` hiện có và xác nhận `Invocable`.
2. Dùng `engine.eval(...)` để nạp script định nghĩa function.
3. Gọi `inv.invokeFunction("functionName", arg1, arg2, ...)`.
4. Kiểm tra/convert `Object` được trả về, và xử lý exceptions phù hợp.

Ví dụ ý tưởng với engine thực thi JavaScript:

```java
// Trích đoạn, chỉ chạy khi engine có provider JavaScript tương thích.
engine.eval("function add(a, b) { return a + b; }");
Invocable inv = (Invocable) engine;  // Chỉ sau khi instanceof đã xác nhận.
Object result = inv.invokeFunction("add", 2, 5);
```

`result` là `Object` vì Java API **không biết trước kiểu trả của script function**. Một provider có thể map kết quả số sang `Integer`, `Double`, kiểu Number khác hoặc wrapper đặc thù. Không nên ép một cách mù quáng:

```java
// Dễ sai nếu provider trả Double thay vì Integer.
Integer exact = (Integer) inv.invokeFunction("add", 2, 5);
```

Nếu hợp đồng nghiệp vụ cho phép lấy số, có thể kiểm tra:

```java
Object raw = inv.invokeFunction("add", 2, 5);
if (!(raw instanceof Number number)) {
    throw new IllegalStateException("add không trả kiểu số.");
}
int result = number.intValue();
```

Đây là **trích đoạn**, không phải lời bảo đảm mọi ngôn ngữ script dùng `Number` cho mọi phép số. `intValue()` có thể làm mất phần thập phân hoặc tràn miền; trong chương trình thật cần validate kiểu, miền giá trị và khả năng mất chính xác.

### 4.1. Hàm không tồn tại khác hàm ném lỗi

- `NoSuchMethodException`: không tìm được function theo tên hoặc kiểu arguments phù hợp.
- `ScriptException`: engine báo lỗi trong quá trình gọi/chạy script.
- `NullPointerException`: tên function truyền vào bằng `null`, theo hợp đồng API.
- Runtime exceptions khác: có thể phát sinh bởi implementation, conversion hoặc code Java tương tác với script.

Đừng bắt `Exception` chung rồi trả `null` cho mọi trường hợp: kết quả script có thể hợp lệ là null, và việc giấu loại lỗi khiến người gọi không biết cần cài provider, bổ sung function hay sửa script.

### 4.2. Hàm toàn cục không đồng nghĩa method của object

`invokeFunction("add", 2, 5)` tìm function ở phạm vi engine hiểu là **top-level/global**. Nếu script chỉ định nghĩa `math.add` như **method trên một object**, `invokeFunction("add", ...)` không nhất thiết tìm được nó. Khi đó dùng `invokeMethod(scriptObject, "add", ...)` hoặc một wrapper function global do script expose.

## 5. `invokeMethod`: gọi method trên script object

Chữ ký:

```java
Object invokeMethod(Object thiz, String name, Object... args)
        throws ScriptException, NoSuchMethodException;
```

Trong JSR 223, `thiz` là **đối tượng của scripting language** được tạo/trả từ một lần đánh giá hay lời gọi trước đó, theo cách engine đại diện nó ở phía Java. Ví dụ minh họa khái niệm:

```javascript
// Script được đánh giá bởi một JSR 223 JavaScript engine tương thích.
var counter = {
    count: 0,
    increment: function (delta) {
        this.count += delta;
        return this.count;
    },
    value: function () {
        return this.count;
    }
};
```

Sau khi `engine.eval(...)` chạy, adapter của provider có thể cho Java lấy object theo bindings:

```java
// Trích đoạn: engine có object "counter" sau khi eval.
Object scriptCounter = engine.get("counter");
Invocable inv = (Invocable) engine;
Object next = inv.invokeMethod(scriptCounter, "increment", 5);
Object current = inv.invokeMethod(scriptCounter, "value");
```

Đây là **trích đoạn phụ thuộc provider**, không phải ví dụ độc lập có output chuẩn. Tên JavaScript, object representation và number conversion phải được kiểm chứng với engine thực tế.

### 5.1. `thiz` không phải receiver Java tùy ý

`Invocable.invokeMethod` **không** được định nghĩa là “gọi Reflection trên bất kỳ Java Object nào”. Theo Java SE 17 API:

- Nếu `thiz == null`, có thể được báo `IllegalArgumentException`.
- Nếu `thiz` không đại diện cho **scripting object** phù hợp mà engine biết, `IllegalArgumentException`.
- Nếu thiếu method hoặc không có chữ ký đối số phù hợp, `NoSuchMethodException`.
- Nếu script method phát sinh lỗi, `ScriptException`.

Đừng truyền `SomeJavaClass.class` vào `invokeMethod` với kỳ vọng nó tự tìm Java static method. Đây là API của **scripting engine**, không phải `Method.invoke`.

Trong ví dụ fixture của bài, `CounterHost` là một **object do fixture quy ước đóng vai script object**. Nó minh họa hợp đồng `thiz` và method dispatch, **không** có nghĩa mọi JSR 223 engine thật phải chấp nhận mọi Java `CounterHost`.

### 5.2. Sự khác biệt giữa `invokeFunction` và `invokeMethod`

| Ý định | API | Tham số chính |
| --- | --- | --- |
| Gọi hàm global `add(a,b)` | `invokeFunction("add",a,b)` | `name` và `args` |
| Gọi method `counter.increment(d)` | `invokeMethod(counter,"increment",d)` | `thiz` + `name` + `args` |
| Gọi Java method `javaObject.apply(x)` bằng Reflection | `method.invoke(javaObject,x)` | `Method` + Java receiver |
| Chạy trực tiếp một đoạn script source | `engine.eval(scriptText)` | Source + context |
| Dùng Java interface cho hàm global | `getInterface(MyApi.class)` | Java interface `Class<T>` |
| Dùng Java interface cho object script | `getInterface(counter,CounterApi.class)` | Script object + Java interface |

Cách phân loại này giúp tránh việc đổi từ `invokeFunction` sang `invokeMethod` chỉ vì hai method cùng chứa chữ “invoke”.

## 6. `getInterface`: ánh xạ script sang Java interface

`Invocable` cung cấp **hai overload**:

```java
<T> T getInterface(Class<T> clasz);

<T> T getInterface(Object thiz, Class<T> clasz);
```

Trong Java API, kết quả có kiểu `T`, là một implementation của interface mà Java caller có thể sử dụng. Engine quyết định cách kết nối method names/signatures sang các script functions hoặc script object members.

### 6.1. Hàm global thành interface Java

Giả sử Java có:

```java
public interface MathOps {
    int add(int a, int b);
    int twice(int x);
}
```

Và script global đã định nghĩa hai hàm tương ứng:

```javascript
function add(a, b) { return a + b; }
function twice(x) { return x * 2; }
```

Sau `eval` và kiểm tra engine implement `Invocable`:

```java
MathOps api = inv.getInterface(MathOps.class);
if (api == null) {
    throw new IllegalStateException("Thiếu hàm tương ứng với MathOps.");
}
int sum = api.add(3, 4);
```

**Ưu điểm:** code Java gọi `api.add(3,4)` với chữ ký Java rõ ràng; không phải lặp lại chuỗi tên `"add"` và ép kiểu `Object` tại mỗi call site.

**Nhược điểm và giới hạn:** interface cần phù hợp với những hàm script mà engine có thể tìm và ánh xạ. Cách chuyển argument/return, hỗ trợ overload, default methods, generics, checked exceptions và chi phí adapter **phụ thuộc engine**. `getInterface` có thể trả **`null`** khi các hàm tương ứng không khả dụng. Không tự động biến mọi script thành một implementation của interface bất kỳ.

### 6.2. Method của script object thành interface Java

Giả sử script tạo object `counter` có method `increment(delta)` và `value()`. Java định nghĩa:

```java
public interface CounterOps {
    int increment(int delta);
    int value();
}
```

Java dùng:

```java
CounterOps api = inv.getInterface(scriptCounter, CounterOps.class);
if (api == null) {
    throw new IllegalStateException("Không ánh xạ được CounterOps.");
}
int next = api.increment(3);
```

Ở đây các Java methods được ánh xạ **lên script object `scriptCounter`**, không lên global functions của engine. Đừng bỏ đối số `scriptCounter` rồi kỳ vọng engine tự đoán “current object”.

### 6.3. Khi nào trả `null`, khi nào ném exception?

| Tình huống | Hành vi chuẩn cần xét |
| --- | --- |
| Interface hợp lệ, đủ functions/methods phù hợp | Có thể trả implementation kiểu `T` |
| Interface hợp lệ nhưng thiếu một hoặc nhiều functions/methods cần thiết | `getInterface(...)` có thể trả **`null`** |
| `clasz == null` hoặc `clasz` không phải interface | `IllegalArgumentException` |
| Với `getInterface(thiz,clasz)`, `thiz==null` hoặc không phải scripting object hợp lệ | `IllegalArgumentException` |
| Sau khi adapter được tạo, script thay đổi / lỗi lúc gọi | Tùy engine và contract của interface; có thể phát sinh exception khi gọi |

Điều quan trọng là **null từ `getInterface` không tương đương `NoSuchMethodException` từ `invokeFunction`**. Một bên là **không tạo được adapter cho interface**, bên kia là **không gọi được hàm theo tên**.

### 6.4. Có phải `getInterface` chính là `java.lang.reflect.Proxy` không?

Không nên khẳng định như vậy cho **mọi scripting engine**. API quy định hành vi và kiểu trả về, **không bắt buộc mọi provider dùng cùng kỹ thuật cài đặt**. Một provider có thể dùng JDK Proxy, cơ chế adapter khác, wrapper riêng hoặc implementation-specific conversion.

Ví dụ **`MiniEngine` tự viết** ở mục 7 **cố ý** dùng `Proxy.newProxyInstance` để hiện thực `getInterface` cho mục đích giảng dạy. Đó là **cách chọn của fixture**, không phải hợp đồng bắt buộc của `Invocable`.

## 7. Ví dụ Java 17+ độc lập, không cần JavaScript engine bên ngoài

### 7.1. Vì sao phải dùng fixture?

Nhiều hướng dẫn cũ viết:

```java
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");
Invocable inv = (Invocable) engine;
```

rồi giả định script engine JavaScript tích hợp luôn có trong JDK. Cách này **không đáng tin trên Java 17** vì Nashorn đã bị loại khỏi JDK từ Java 15. Nếu bài học dùng trực tiếp JavaScript mà không cài provider, ví dụ có thể thất bại trước khi kiểm tra `Invocable`.

Để cô lập đúng khái niệm, chương trình sau có:

- `PlainEngine` kế thừa `AbstractScriptEngine`, **không** implement `Invocable`.
- `MiniEngine` kế thừa `PlainEngine` và **implement `Invocable`**; `eval("install")` đánh dấu các hàm “đã được nạp”.
- `invokeFunction` hỗ trợ `add`, `twice`, và một hàm `explode` cố tình ném `ScriptException`.
- `invokeMethod` hỗ trợ `increment` và `value` trên một `CounterHost` đóng vai script object.
- `getInterface(Class<T>)` tạo adapter cho `MathOps`.
- `getInterface(Object,Class<T>)` tạo adapter cho `CounterOps` với một receiver cụ thể.
- `MissingOps` minh họa tình huống interface **không có functions tương ứng**, trả `null`.
- Các trường hợp sai tên method, script error, receiver không hợp lệ và type không phải interface được kiểm tra.

**Giới hạn minh bạch:** `PlainEngine.getFactory()` trả `null` vì ví dụ không đăng ký provider với `ScriptEngineManager`; `MiniEngine` chỉ nhận đúng từ khóa `"install"`, **không parse JavaScript**. Mục tiêu là kiểm thử contract của `Invocable` bằng code không phụ thuộc engine bên ngoài.

### 7.2. Mã đầy đủ: `InvocableApiDemo.java`

Tạo một file **`InvocableApiDemo.java`** chứa:

```java
import java.io.IOException;
import java.io.Reader;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Objects;
import javax.script.AbstractScriptEngine;
import javax.script.Bindings;
import javax.script.Invocable;
import javax.script.ScriptContext;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineFactory;
import javax.script.ScriptException;
import javax.script.SimpleBindings;

public class InvocableApiDemo {
    public interface MathOps {
        int add(int a, int b);
        int twice(int x);
    }

    public interface CounterOps {
        int increment(int delta);
        int value();
    }

    public interface MissingOps {
        int unavailable();
    }

    static final class CounterHost {
        private int number;

        int increment(int delta) {
            number += delta;
            return number;
        }

        int value() {
            return number;
        }
    }

    // Fixture tối giản: KHÔNG phải JavaScript interpreter / registered provider.
    static class PlainEngine extends AbstractScriptEngine {
        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            return script;
        }

        @Override
        public Object eval(Reader reader, ScriptContext context)
                throws ScriptException {
            StringBuilder result = new StringBuilder();
            char[] buffer = new char[256];
            try {
                int size;
                while ((size = reader.read(buffer)) != -1) {
                    result.append(buffer, 0, size);
                }
            } catch (IOException ex) {
                throw new ScriptException(ex);
            }
            return eval(result.toString(), context);
        }

        @Override
        public Bindings createBindings() {
            return new SimpleBindings();
        }

        @Override
        public ScriptEngineFactory getFactory() {
            return null; // Fixture không có factory để ScriptEngineManager khám phá.
        }
    }

    static final class MiniEngine extends PlainEngine implements Invocable {
        private boolean installed;

        @Override
        public Object eval(String script, ScriptContext context)
                throws ScriptException {
            if (!"install".equals(script.trim())) {
                throw new ScriptException("Unsupported fixture script");
            }
            installed = true;
            return "ready";
        }

        private static boolean globalExists(String name) {
            return "add".equals(name) || "twice".equals(name)
                    || "explode".equals(name);
        }

        private static boolean memberExists(String name) {
            return "increment".equals(name) || "value".equals(name);
        }

        @Override
        public Object invokeFunction(String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            Objects.requireNonNull(name, "name");
            if (!installed || !globalExists(name)) {
                throw new NoSuchMethodException(name);
            }
            Object[] actual = args == null ? new Object[0] : args;
            switch (name) {
                case "add":
                    if (actual.length != 2
                            || !(actual[0] instanceof Integer)
                            || !(actual[1] instanceof Integer)) {
                        throw new ScriptException("add needs two integers");
                    }
                    return (int) actual[0] + (int) actual[1];
                case "twice":
                    if (actual.length != 1
                            || !(actual[0] instanceof Integer)) {
                        throw new ScriptException("twice needs one integer");
                    }
                    return (int) actual[0] * 2;
                case "explode":
                    throw new ScriptException("simulated script error");
                default:
                    throw new NoSuchMethodException(name);
            }
        }

        @Override
        public Object invokeMethod(Object thiz, String name, Object... args)
                throws ScriptException, NoSuchMethodException {
            Objects.requireNonNull(name, "name");
            if (!(thiz instanceof CounterHost host)) {
                throw new IllegalArgumentException("not a fixture script object");
            }
            if (!installed || !memberExists(name)) {
                throw new NoSuchMethodException(name);
            }
            Object[] actual = args == null ? new Object[0] : args;
            switch (name) {
                case "increment":
                    if (actual.length != 1
                            || !(actual[0] instanceof Integer)) {
                        throw new ScriptException("increment needs an integer");
                    }
                    return host.increment((int) actual[0]);
                case "value":
                    if (actual.length != 0) {
                        throw new ScriptException("value takes no arguments");
                    }
                    return host.value();
                default:
                    throw new NoSuchMethodException(name);
            }
        }

        @Override
        public <T> T getInterface(Class<T> iface) {
            return adapt(null, iface);
        }

        @Override
        public <T> T getInterface(Object thiz, Class<T> iface) {
            if (!(thiz instanceof CounterHost)) {
                throw new IllegalArgumentException("not a fixture script object");
            }
            return adapt(thiz, iface);
        }

        private <T> T adapt(Object thiz, Class<T> iface) {
            if (iface == null || !iface.isInterface()) {
                throw new IllegalArgumentException("expected an interface");
            }
            if (!installed) {
                return null;
            }
            for (Method method : iface.getMethods()) {
                if (method.getDeclaringClass() == Object.class) continue;
                if (thiz == null ? !globalExists(method.getName())
                        : !memberExists(method.getName())) {
                    return null;
                }
            }

            Object proxy = Proxy.newProxyInstance(
                    iface.getClassLoader(), new Class<?>[]{iface},
                    (receiver, method, args) -> {
                        if (method.getDeclaringClass() == Object.class) {
                            return switch (method.getName()) {
                                case "toString" -> "InvocableFixtureProxy";
                                case "hashCode" ->
                                        System.identityHashCode(receiver);
                                case "equals" -> receiver == args[0];
                                default -> throw new UnsupportedOperationException();
                            };
                        }

                        Object[] values =
                                args == null ? new Object[0] : args;
                        return thiz == null
                                ? invokeFunction(method.getName(), values)
                                : invokeMethod(thiz, method.getName(), values);
                    });
            return iface.cast(proxy);
        }
    }

    public static void main(String[] args) throws Exception {
        ScriptEngine plain = new PlainEngine();
        ScriptEngine engine = new MiniEngine();
        System.out.println("plain Invocable=" + (plain instanceof Invocable));
        System.out.println("mini Invocable=" + (engine instanceof Invocable));

        if (!(engine instanceof Invocable inv)) {
            throw new IllegalStateException("Engine does not implement Invocable");
        }

        System.out.println("interface before eval="
                + (inv.getInterface(MathOps.class) == null));

        System.out.println("eval=" + engine.eval("install"));
        System.out.println("invoke add=" + inv.invokeFunction("add", 2, 5));
        System.out.println("invoke twice=" + inv.invokeFunction("twice", 6));

        try {
            inv.invokeFunction("missing");
        } catch (NoSuchMethodException ex) {
            System.out.println("missing=" + ex.getClass().getSimpleName());
        }

        try {
            inv.invokeFunction("explode");
        } catch (ScriptException ex) {
            System.out.println("script failure=" + ex.getClass().getSimpleName());
        }

        MathOps math = inv.getInterface(MathOps.class);
        System.out.println("global mapping=" + (math != null));
        System.out.println("interface add=" + math.add(3, 4));
        System.out.println("interface twice=" + math.twice(8));
        System.out.println("missing interface="
                + (inv.getInterface(MissingOps.class) == null));

        CounterHost host = new CounterHost();
        System.out.println("method increment="
                + inv.invokeMethod(host, "increment", 5));
        System.out.println("method value="
                + inv.invokeMethod(host, "value"));

        CounterOps counter = inv.getInterface(host, CounterOps.class);
        System.out.println("object mapping=" + (counter != null));
        System.out.println("interface increment=" + counter.increment(3));
        System.out.println("interface value=" + counter.value());

        try {
            inv.invokeMethod(null, "value");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid receiver="
                    + ex.getClass().getSimpleName());
        }

        try {
            inv.getInterface(String.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("not interface="
                    + ex.getClass().getSimpleName());
        }
    }
}
```

### 7.3. Biên dịch và chạy

Dùng **JDK 17 trở lên** trong thư mục chứa file:

```bash
javac --release 17 InvocableApiDemo.java
java InvocableApiDemo
```

**Stdout chính xác đã kiểm chứng khi chạy trên JDK có Java 17 APIs:**

```text
plain Invocable=false
mini Invocable=true
interface before eval=true
eval=ready
invoke add=7
invoke twice=12
missing=NoSuchMethodException
script failure=ScriptException
global mapping=true
interface add=7
interface twice=16
missing interface=true
method increment=5
method value=5
object mapping=true
interface increment=8
interface value=8
invalid receiver=IllegalArgumentException
not interface=IllegalArgumentException
```

Cả `javac --release 17` và `java` đã chạy với **exit code 0** trong phép kiểm chứng. Chương trình **không phụ thuộc Nashorn, GraalJS hay bất cứ thư viện bên ngoài nào**, vì chính `MiniEngine` cung cấp API `Invocable` mô phỏng.

### 7.4. Đọc kết quả nhóm engine-capability

```text
plain Invocable=false
mini Invocable=true
interface before eval=true
eval=ready
```

- `PlainEngine` chỉ có `ScriptEngine`, không có `Invocable`. Phép `instanceof` trả false, nên không được ép nó thành `Invocable`.
- `MiniEngine` implement `Invocable`, trả true; code giữ biến `inv` với kiểu chính xác.
- Trước `eval("install")`, các hàm fixture chưa sẵn sàng nên `getInterface(MathOps.class)` trả null; vì vậy `interface before eval=true`.
- Sau `eval`, fixture bật cờ `installed` và trả chuỗi `ready`.

Đây là ví dụ “**khả năng engine**” khác với “**hàm đã sẵn sàng trong engine**”. `instanceof Invocable` cho biết API được hỗ trợ, không bảo đảm script đã được đánh giá hoặc có bất kỳ hàm nào.

### 7.5. Đọc kết quả nhóm gọi hàm và lỗi

```text
invoke add=7
invoke twice=12
missing=NoSuchMethodException
script failure=ScriptException
```

`invokeFunction("add",2,5)` tìm hàm global `add` đã “installed” và trả 7. `twice(6)` trả 12. `invokeFunction("missing")` không tìm được hàm nên ném `NoSuchMethodException`. `invokeFunction("explode")` tìm được hàm nhưng cố tình ném `ScriptException`.

**Phân biệt rõ:** “không tìm thấy hàm” và “hàm chạy nhưng bị lỗi” không phải một exception. Trong engine thật, `ScriptException` còn có thể chứa file name/line/column hoặc nguyên nhân cụ thể tùy provider.

### 7.6. Đọc kết quả nhóm ánh xạ interface global

```text
global mapping=true
interface add=7
interface twice=16
missing interface=true
```

`getInterface(MathOps.class)` thành công vì fixture thấy cả `add` và `twice`. Java có thể gọi `math.add(3,4)` và `math.twice(8)` bằng interface methods có kiểu `int`. `MissingOps` yêu cầu `unavailable()`, mà fixture không có function đó nên `getInterface(MissingOps.class)` trả `null`; phép so sánh `==null` in true.

Trong fixture, JDK Proxy chuyển mỗi method interface sang `invokeFunction`, nhưng đó là **quyết định cài đặt của MiniEngine**. Với engine thật, thời điểm tạo adapter, mapping overload/arguments và các chuyển đổi có thể khác nhau.

### 7.7. Đọc kết quả nhóm script-object mapping

```text
method increment=5
method value=5
object mapping=true
interface increment=8
interface value=8
```

Trước khi lấy adapter, Java gọi `invokeMethod(host,"increment",5)`, làm `CounterHost.number` từ 0 lên 5; `invokeMethod(host,"value")` trả 5. `getInterface(host,CounterOps.class)` tạo view gắn với **chính host ấy**; gọi `counter.increment(3)` tăng từ 5 lên 8, `counter.value()` trả 8.

Đây là cách quan sát rõ ràng **object-bound adapter** khác với **global adapter**: đối tượng đích là một input quan trọng. Tuy nhiên, `CounterHost` ở đây chỉ là model đối tượng script mà **fixture** chủ động công nhận; trong JavaScript engine thực tế, phải dùng object do engine tạo/trả.

### 7.8. Đọc kết quả nhóm tham số không hợp lệ

```text
invalid receiver=IllegalArgumentException
not interface=IllegalArgumentException
```

- `invokeMethod(null,"value")` không có script object receiver hợp lệ, nên fixture ném `IllegalArgumentException` đúng ý nghĩa contract.
- `getInterface(String.class)` dùng `String` là **class**, không phải interface, nên ném `IllegalArgumentException`.

Trong code thật còn cần guard `engine==null`, `name==null` và thiếu function. Các trường hợp này không được gộp với “không có adapter cho interface”.

## 8. Ví dụ có điều kiện với JavaScript engine thật

Phần này cho thấy cách dùng `Invocable` với một provider có thể đánh giá JavaScript. **Không cam kết chạy chỉ với JDK 17 mặc định**. Trước khi chạy cần cài đặt, cấu hình và kiểm tra một **JSR 223 JavaScript engine provider tương thích** (ví dụ một engine từ bên thứ ba cung cấp `ScriptEngineFactory`/`Invocable`).

### 8.1. Chuẩn bị JavaScript

Đoạn script sau định nghĩa hàm global và một object:

```javascript
function add(a, b) {
    return a + b;
}

function twice(x) {
    return x * 2;
}

var counter = {
    count: 0,
    increment: function (delta) {
        this.count += delta;
        return this.count;
    },
    value: function () {
        return this.count;
    }
};
```

Đây là **JavaScript source**, không phải Java code. Nó chỉ được thực thi khi engine được cài có hỗ trợ cú pháp và cách expose global functions/objects như ví dụ.

### 8.2. Java code kiểm tra engine trước khi sử dụng

```java
import javax.script.Invocable;
import javax.script.ScriptEngine;
import javax.script.ScriptEngineManager;

// Trích đoạn: đặt trong một method khai báo throws Exception.
ScriptEngine engine =
        new ScriptEngineManager().getEngineByName("JavaScript");

if (engine == null) {
    throw new IllegalStateException(
            "Chưa cài JSR 223 JavaScript provider phù hợp");
}
if (!(engine instanceof Invocable inv)) {
    throw new IllegalStateException(
            "Provider không hỗ trợ Invocable");
}

engine.eval("""
        function add(a,b) { return a+b; }
        var counter = {
            count: 0,
            increment: function(d) {
                this.count += d;
                return this.count;
            },
            value: function() { return this.count; }
        };
        """);

Object rawSum = inv.invokeFunction("add", 2, 5);
Object scriptCounter = engine.get("counter");
Object rawNext = inv.invokeMethod(
        scriptCounter, "increment", 3);
```

**Không có stdout chuẩn** cho đoạn trích này: `rawSum`/`rawNext` có thể được provider ánh xạ thành các Java wrapper types khác nhau, và cách expose `counter` có thể khác. Đây là **mẫu tích hợp có điều kiện**, không phải phép thử độc lập như `InvocableApiDemo.java`.

Sau khi xác minh engine hỗ trợ ánh xạ interface:

```java
// Trích đoạn: MathOps/CounterOps là Java interfaces đã khai báo.
// Biến inv/scriptCounter có từ đoạn trên.
MathOps global = inv.getInterface(MathOps.class);
CounterOps bound = inv.getInterface(scriptCounter, CounterOps.class);

if (global == null || bound == null) {
    throw new IllegalStateException(
            "Provider không ánh xạ được các script functions.");
}

int sum = global.add(2, 5);
int now = bound.increment(3);
```

Đặc biệt, kiểm tra **numeric conversions**. Một engine có thể trả `Double` khi gọi `invokeFunction` nhưng convert thành Java `int` khi gọi qua adapter theo hợp đồng provider. Không dựa vào điều đó nếu chưa xác nhận bằng kiểm thử của engine thực tế.

### 8.3. Nếu không có JavaScript engine thì sao?

JSR 223 **là API**, không phải một cam kết rằng mọi ngôn ngữ đều được cài sẵn. Java 17 không chứa Nashorn. Bạn có thể:

- Dùng scripting engine khác có `ScriptEngineFactory` và `Invocable` phù hợp.
- Thêm dependency/provider JavaScript hỗ trợ JSR 223 theo tài liệu của nó.
- Nếu provider không implement `Invocable`, cân nhắc engine-specific invocation APIs, wrapper function trong `eval` hoặc chọn engine khác.
- Nếu chỉ cần một vài quy tắc cấu hình, dùng Java function/strategy hoặc DSL an toàn mà không nhất thiết nhúng engine.

Không nên đưa một thư viện script quá cũ vào production chỉ để tái hiện ví dụ Java 8 mà không xem compatibility, bảo trì, security và module requirements.

## 9. Xử lý kiểu đối số và giá trị trả về

### 9.1. Java `Object... args` không quy định conversion của mọi engine

Cả hai method đều dùng `Object...`:

```java
inv.invokeFunction("add", 2, 5);
inv.invokeMethod(scriptObject, "increment", 3);
```

Ở Java call site, primitive `int` thường được boxing thành `Integer` trước khi truyền vào `Object[]`. **Sau đó**, engine quyết định mapping từ Java object sang kiểu script theo tài liệu provider. Cần tránh suy luận rằng `Integer` ở Java chắc chắn đến script như một “integer exact 32-bit” với mọi engine.

Đối với script numbers, dates, arrays, maps, callbacks hoặc objects, mapping có thể provider-specific. Luôn làm rõ giao thức dữ liệu giữa Java và script, nhất là khi ứng dụng cần độ chính xác tiền tệ hoặc schema ổn định.

### 9.2. `null` và lời gọi không tham số

Với lời gọi Java:

```java
Object result = inv.invokeFunction("noArg");
```

Java truyền một mảng varargs rỗng khi gọi theo cách thông thường. Nếu caller truyền rõ `(Object[]) null`, implementation có thể nhận giá trị `args` null; không nên làm vậy trừ khi API/provider định nghĩa cách xử lý mong muốn.

`MiniEngine` trong ví dụ dùng:

```java
Object[] actual = args == null ? new Object[0] : args;
```

để bảo đảm code fixture không bị `NullPointerException`. Đó là lựa chọn của fixture, không có nghĩa mọi `Invocable` provider phải xử lý `null args` giống vậy.

Ngoài ra, `invokeFunction("f", (Object) null)` chuyển **một argument Java null**, khác với truyền null cho **cả varargs array** bằng `(Object[])null`. Khi tích hợp, hãy test cả ba trường hợp nếu cần.

### 9.3. Script result có thể là null

`invokeFunction` và `invokeMethod` trả `Object`; một function script có thể trả `null` hoặc tương đương ngôn ngữ đó. Đừng lẫn:

- `getInterface(...) == null`: không tạo được Java interface adapter.
- `invokeFunction(...) == null`: function đã được gọi và **giá trị trả** là null (tùy provider semantics).
- `engine == null`: chưa tìm được engine.
- `ScriptException`: quá trình eval/invocation có lỗi.

Cả bốn biểu hiện cần được chẩn đoán riêng để tránh code sản phẩm coi mọi null là cùng một lỗi.

### 9.4. Primitive return trên interface

Khi interface khai báo:

```java
public interface MathOps {
    int add(int a, int b);
}
```

adapter phải trả giá trị tương thích với `int` Java. Nếu engine/proxy trả `null` hoặc sai wrapper, lời gọi có thể ném `NullPointerException` hay `ClassCastException` trong lúc unbox/cast. Với provider thật, các quy tắc conversion có thể hỗ trợ nhiều loại số; hãy kiểm tra kết quả thực tế thay vì giả định.

### 9.5. Checked exceptions ở lớp adapter

`Invocable.invokeFunction` và `invokeMethod` có các checked exceptions `ScriptException` và `NoSuchMethodException`. Nhưng interface Java ánh xạ bằng `getInterface` có thể **không khai báo hai exception đó**:

```java
public interface MathOps {
    int add(int a, int b);
}
```

Khi script gặp lỗi bên dưới adapter, hành vi bọc/chuyển exception phụ thuộc provider/proxy implementation và signature của interface. Nếu adapter dùng JDK Proxy mà handler ném checked exception không được interface khai báo, caller có thể gặp `UndeclaredThrowableException`. Đừng viết error handler chỉ bắt `ScriptException` quanh `math.add(...)` khi interface không khai báo nó, rồi chắc chắn tin mình bắt được mọi lỗi.

Cách thiết kế có thể cân nhắc: giao diện khai báo exceptions phù hợp, adapter policy chuyển lỗi thành unchecked domain exception, hoặc sử dụng `invokeFunction` trực tiếp để giữ nguyên checked exceptions của `Invocable` khi cần chẩn đoán chi tiết.

## 10. Xử lý lỗi có cấu trúc

| Trường hợp | Lỗi/giá trị cần nhận biết | Cách xử lý |
| --- | --- | --- |
| `getEngineByName("JavaScript")` không có provider | `engine == null` | Cài/đăng ký provider hoặc disable feature có thông báo |
| Engine không implement `Invocable` | `instanceof Invocable == false` | Không cast; dùng API provider hoặc engine phù hợp |
| Script chưa được `eval`/nạp | Không có function/method tương ứng | Nạp script rồi mới gọi; kiểm tra context/bindings |
| Tên function/method truyền null | `NullPointerException` theo API | Validate tên trước gọi |
| Tên function hoặc signature không tìm thấy | `NoSuchMethodException` | Kiểm tra namespace, spelling, số/kiểu đối số |
| Script method/function ném lỗi | `ScriptException` khi gọi trực tiếp | Đọc message, nguyên nhân và metadata script |
| `invokeMethod` với `thiz==null`/không phải script object | `IllegalArgumentException` | Giữ đúng object từ engine |
| `getInterface` với một class không phải interface | `IllegalArgumentException` | Chỉ truyền interface `Class<T>` |
| Không map được các methods của interface | `getInterface(...) == null` | So sánh method names/signatures, provider support |
| Adapter trả null cho primitive Java | Có thể `NullPointerException` | Đặt hợp đồng return/conversion rõ |
| Adapter dùng JDK Proxy ném checked exception không được khai báo | Có thể `UndeclaredThrowableException` | Kiểm tra exception policy |
| Engine không tìm đúng object do context/scope thay đổi | Missing function/member hoặc lỗi engine-specific | Rà soát `Bindings` và `ScriptContext` |
| Code script không tin cậy chạy trong process | **Rủi ro bảo mật** | Cách ly/thẩm định, không coi `ScriptEngine` là sandbox |

### 10.1. Mẫu phân luồng exceptions của lời gọi trực tiếp

```java
// Trích đoạn, giả định engine/Invocable đã sẵn sàng.
try {
    Object result = inv.invokeFunction("calculate", 2, 5);
    // Validate result theo schema hợp đồng.
} catch (NoSuchMethodException ex) {
    // Tên hoặc signature không khớp.
} catch (ScriptException ex) {
    // Script chạy lỗi / engine báo lỗi.
}
```

Đừng dùng `catch(Throwable)` rồi trả default để che `OutOfMemoryError` hoặc các lỗi VM nghiêm trọng. Ứng dụng có thể thêm domain-specific error types cho service boundary, nhưng không nên đánh mất cause và context cần chẩn đoán.

### 10.2. Phân biệt lỗi tại `eval` và lỗi tại `invoke`

Một function có thể định nghĩa được nhưng chỉ ném lỗi khi chạy:

```javascript
function laterFailure() {
    throw new Error("failure while invoking");
}
```

Engine có thể `eval` thành công vì source hợp lệ; lỗi chỉ xuất hiện khi `invokeFunction("laterFailure")`. Ngược lại, syntax error khi `eval` có thể ném `ScriptException` **trước khi bất cứ function nào được đăng ký thành công**.

Vì thế pipeline nên ghi tách:

1. **Engine discovery**.
2. **Capability check (`Invocable`)**.
3. **Script loading / `eval`**.
4. **Function/method lookup và invocation**.
5. **Result/exception conversion**.

Đưa tất cả vào một block `catch(Exception)` duy nhất sẽ làm khó phân biệt lỗi deployment với lỗi script business logic.

## 11. Thread safety, scope, lifecycle và hiệu năng

### 11.1. Không giả định một engine là thread-safe

`ScriptEngine` có thể giữ biến global, object script, module cache hoặc interpreter state. Sự an toàn khi nhiều thread chia sẻ engine phụ thuộc provider. Một số engine cung cấp metadata `"THREADING"` qua `ScriptEngineFactory.getParameter(...)`, nhưng giá trị đó cần hiểu theo tài liệu của nhà cung cấp; không mặc định mọi engine có cùng mức đồng bộ.

Tránh chia sẻ bừa một script object stateful và interface adapter giữa nhiều request đồng thời. Có thể:

- Tạo **engine instance riêng** cho mỗi request/session có state riêng.
- Đặt synchronization/lock nếu provider hỗ trợ mô hình share nhưng không thread-safe.
- Dùng engine pool và isolation theo tenant nếu có lý do hiệu năng.
- Hạn chế số lượng scripts/objects được nạp và quản lý lifecycle.

### 11.2. `Bindings` và `ScriptContext` ảnh hưởng nơi tìm function

Khi chạy `eval`, engine có thể lưu state trong scope của `ENGINE_SCOPE`/`GLOBAL_SCOPE` và một `ScriptContext`. Nếu bạn `eval` trong một context khác rồi sau đó `invokeFunction` trên engine dùng state/context khác, function có thể không tìm thấy. Cách lưu function object, lifetime và binding rules phụ thuộc engine.

Hãy thiết kế rõ ràng “script được load vào engine nào, context nào, và adapter được tạo từ trạng thái nào”. Không giả định một engine mới có thể gọi những hàm đã load trong một engine cũ chỉ vì chúng có cùng language name.

### 11.3. Chi phí gọi lại hàm và interface view

`Invocable` tránh việc nối chuỗi và `eval("func(...)")` lặp lại mỗi lời gọi, và `getInterface` giúp Java caller giữ API có kiểu. Tuy nhiên, có thể vẫn tồn tại overhead:

- Dispatch theo tên trong interpreter.
- Conversion Java ↔ script values.
- Marshalling arguments/return.
- Adapter/proxy layer khi dùng interface mapping.
- Đồng bộ nếu engine được chia sẻ nhiều thread.

Không khẳng định `getInterface` luôn nhanh hơn `invokeFunction` hoặc ngược lại nếu chưa benchmark đúng provider. Hãy đo theo workload với warm-up, dữ liệu thực tế và số lời gọi tương ứng.

### 11.4. Không nên cache adapter vô thời hạn nếu script state thay đổi

Một adapter `getInterface` có thể tham chiếu engine, script object, bindings hoặc class loader. Nếu script được reload hoặc object context đã hết hạn, adapter cũ có thể không còn phản ánh trạng thái mới, tùy provider.

Cách quản lý tốt:

- Gắn adapter với **version** của script/engine và một lifecycle rõ.
- Loại bỏ reference tới engine/object không còn dùng.
- Khi reload, kiểm thử lại các method hợp đồng, tạo adapter mới nếu cần.
- Đảm bảo những thay đổi state shared được đồng bộ đúng cách.

## 12. An toàn khi nhúng kịch bản

### 12.1. `ScriptEngine` không tự tạo sandbox

Một script engine chạy trong JVM của ứng dụng có thể có khả năng tương tác với Java host objects, filesystem, network, process hoặc data sources tùy provider configuration. **Không coi `Invocable`, `getInterface` hay `ScriptEngineManager` là cơ chế giới hạn quyền**.

Nếu nội dung script đến từ người dùng không tin cậy, cần lựa chọn:

- Một **ngôn ngữ/DSL giới hạn** và validation AST phù hợp.
- Scripting provider có mô hình host access restrictions được cấu hình đúng.
- Isolation tại mức process/container/VM với giới hạn CPU, RAM, thời gian, filesystem, network và credentials.
- Kiểm soát số lượng scripts, thời gian chạy, recursion và object lifetime.
- Đánh giá threat model, không dựa vào Java security manager cũ như một phương án mặc định.

Chỉ vì `getInterface` làm script trông như một Java object có kiểu **không** có nghĩa code script an toàn hoặc đáng tin.

### 12.2. Không ghép input trực tiếp vào script source khi có thể truyền args

Cách dễ gặp rủi ro:

```java
// PHẢN VÍ DỤ khi userInput không tin cậy.
engine.eval("perform('" + userInput + "')");
```

Một giá trị chứa dấu nháy hoặc mã điều khiển có thể phá cấu trúc source và gây script injection. Nếu function đã được định nghĩa và engine hỗ trợ `Invocable`, truyền dữ liệu **như arguments** thường rõ ràng hơn:

```java
Object result = inv.invokeFunction("perform", userInput);
```

Cách này không biến input thành JavaScript source trong chính lời gọi. Tuy nhiên, script đã load vẫn có thể xử lý input không an toàn; cần validate/escape theo tầng downstream (SQL, HTML, shell...) và host access policy.

### 12.3. Ranh giới Java ↔ script cần hợp đồng dữ liệu

Một interface typed view là API Java nhưng ở bên dưới là logic scripting có thể thay đổi. Nên có:

- Method names và input/output schema rõ ràng.
- Chính sách null và numeric precision.
- Chính sách timeout/cancellation; không giả định `Thread.interrupt` luôn dừng script.
- Logging diagnostics có context nhưng không rò rỉ secrets.
- Giới hạn khả năng gọi host Java APIs từ script và giới hạn resource consumption.

## 13. Cách chọn `invokeFunction`, `invokeMethod` hay `getInterface`

| Mục tiêu | Phương pháp | Lý do |
| --- | --- | --- |
| Gọi một top-level function theo tên | `invokeFunction(name,args)` | Đơn giản, phản hồi trực tiếp, phù hợp function name động |
| Gọi một method của script object | `invokeMethod(thiz,name,args)` | Giữ đúng receiver/object state |
| Có Java interface ổn định ánh xạ tới functions global | `getInterface(Api.class)` | Java caller có API typed, không viết tên hàm bằng chuỗi mỗi lần |
| Có Java interface ổn định ánh xạ tới một script object | `getInterface(scriptObject,Api.class)` | Tạo typed view gắn với state của object |
| Chỉ cần đánh giá một script block và nhận kết quả | `ScriptEngine.eval(source)` | Không bắt buộc engine implement `Invocable` |
| Chỉ có Java method cần gọi | Reflection/MethodHandle/call thường | Không cần nhúng scripting |
| Engine không implement `Invocable` | Engine-specific API hoặc đổi provider | Không được cast mù |
| Script provider có hàm chưa được load | `eval`/load trước | Capability check không đảm bảo function existence |

### 13.1. Mẫu tích hợp có kiểm tra hợp đồng

```java
// Trích đoạn khung kiến trúc, không phải chương trình độc lập.
ScriptEngine engine = provider.getEngine(); // Provider đã được cấu hình.
if (engine == null) {
    throw new IllegalStateException("Missing script engine");
}
if (!(engine instanceof Invocable inv)) {
    throw new IllegalStateException("Engine is not Invocable");
}

engine.eval(verifiedScriptSource);
Api api = inv.getInterface(Api.class);
if (api == null) {
    throw new IllegalStateException("Script does not implement Api");
}

// Dùng api trong vòng đời của engine và script tương ứng.
```

`provider`, `Api` và `verifiedScriptSource` là **các ký hiệu minh họa** để diễn tả cách tổ chức ứng dụng, không phải mã chạy độc lập. Trong chương trình chính, mọi type/field cần thiết đều có định nghĩa.

Lợi ích của mẫu trên là **fail fast tại boundary**: không để một `ClassCastException` hoặc `NullPointerException` mơ hồ xuất hiện sau khi ứng dụng đã bắt đầu xử lý request.

## 14. Bài tập và câu hỏi tự kiểm tra

**Câu 1.** Có một `ScriptEngine` từ `ScriptEngineManager`. Có thể cast ngay sang `Invocable` không?  
**Đáp án:** Không. `Invocable` là interface tùy chọn. Cần bảo đảm engine khác null và `instanceof Invocable` trước khi cast.

**Câu 2.** Java 17 có đảm bảo `getEngineByName("JavaScript")` trả engine không?  
**Đáp án:** Không. Nashorn được gỡ khỏi JDK từ Java 15. Phải cài/đăng ký provider JavaScript JSR 223 phù hợp nếu muốn dùng.

**Câu 3.** `eval("function add...")` thành công nhưng `invokeFunction("multiply",2,3)` không tìm được hàm. Lỗi API dự kiến là gì?  
**Đáp án:** `NoSuchMethodException` nếu function name hoặc kiểu arguments phù hợp không được tìm thấy.

**Câu 4.** `invokeFunction("explode")` tìm được hàm nhưng script throw error. Có phải `NoSuchMethodException` không?  
**Đáp án:** Không. Engine thường báo `ScriptException` cho lỗi thực thi script. Ví dụ MiniEngine cố ý minh họa hai exception khác nhau.

**Câu 5.** Muốn gọi `counter.increment(3)` trên script object, dùng API nào?  
**Đáp án:** `inv.invokeMethod(scriptCounter,"increment",3)`, với `scriptCounter` phải là object phù hợp do engine nhận diện.

**Câu 6.** `invokeFunction("increment",3)` có tự tìm method của `scriptCounter` không?  
**Đáp án:** Không được bảo đảm. `invokeFunction` dành cho top-level functions. Với method gắn object dùng `invokeMethod`.

**Câu 7.** Java có `MathOps` khai báo `add` và `twice`, còn script chỉ có `add`. `getInterface(MathOps.class)` có chắc thành công không?  
**Đáp án:** Không. Nếu các functions tương ứng không sẵn có, `getInterface` có thể trả null. Cần kiểm tra kết quả trước khi gọi.

**Câu 8.** Hai overload `getInterface` khác nhau ở đâu?  
**Đáp án:** `getInterface(Class<T>)` tìm mapping từ **global functions**; `getInterface(Object,Class<T>)` tìm mapping từ **member functions của script object** được truyền vào.

**Câu 9.** `getInterface(String.class)` có hợp lệ không?  
**Đáp án:** Không. `String.class` không phải interface; API ném `IllegalArgumentException`.

**Câu 10.** `getInterface(MathOps.class)` trả `null` có giống `invokeFunction("add")` trả `null` không?  
**Đáp án:** Không. Cái trước là không tạo được adapter; cái sau có thể là function hợp lệ trả giá trị null.

**Câu 11.** Một engine implement `Invocable` nhưng chưa `eval` script định nghĩa hàm. `instanceof` true có đảm bảo `invokeFunction` thành công không?  
**Đáp án:** Không. Capability và state đã nạp là hai điều khác nhau. Cần load/eval trước và kiểm tra function/method thực sự tồn tại.

**Câu 12.** `invokeMethod(null,"value")` được phép không?  
**Đáp án:** Không. `thiz` cần script object hợp lệ; API nêu `IllegalArgumentException` khi receiver null/không đúng.

**Câu 13.** Tại sao không ép kết quả mọi `invokeFunction("sum")` thành `Integer`?  
**Đáp án:** Mapping số Java ↔ script là implementation-specific. Có engine trả `Double` hoặc kiểu khác; cần kiểm tra type/schema và conversion rõ ràng.

**Câu 14.** Interface trả `int` nhưng script trả null. Điều gì có thể xảy ra?  
**Đáp án:** Adapter có thể ném `NullPointerException` lúc unbox (hoặc lỗi conversion theo provider). Cần định nghĩa hợp đồng return type và xử lý null.

**Câu 15.** `getInterface` có được chuẩn Java bắt buộc hiện thực bằng JDK Proxy không?  
**Đáp án:** Không. API chỉ yêu cầu trả implementation tương thích hoặc null khi unavailable. Fixture trong bài dùng Proxy làm ví dụ.

**Câu 16.** Một script không tin cậy được chạy bằng `ScriptEngine` trong JVM server. `Invocable` có tự cô lập quyền truy cập không?  
**Đáp án:** Không. Cần threat model, host access restrictions và isolation phù hợp; typed interface không tạo sandbox.

**Câu 17.** Hai thread cùng gọi method trên một object script stateful. Có thể giả định an toàn không?  
**Đáp án:** Không. Cần xem thread-safety của provider và giới hạn chia sẻ state/context, có thể dùng engine per session hoặc synchronization.

**Câu 18.** Vì sao truyền `userInput` như `invokeFunction("perform",userInput)` thường tốt hơn nối vào chuỗi `eval(...)`?  
**Đáp án:** Tránh biến dữ liệu đầu vào thành script source trong lời gọi, giảm nguy cơ script injection từ quá trình ghép raw strings, dù vẫn cần validate và sandbox/isolation riêng.

## 15. Tóm tắt và tài liệu chính thức

**Ghi nhớ bốn API của `Invocable`:**

```text
invokeFunction("name", args...)
    -> gọi function global; trả Object

invokeMethod(scriptObject, "name", args...)
    -> gọi method trên script object; trả Object

getInterface(JavaInterface.class)
    -> typed view từ global functions; có thể null

getInterface(scriptObject, JavaInterface.class)
    -> typed view từ methods của object; có thể null
```

**Checklist dùng an toàn:**

1. Tìm engine và xác nhận `engine != null`.
2. Kiểm tra `engine instanceof Invocable` trước khi cast.
3. `eval`/load script vào đúng engine/context.
4. Gọi `invokeFunction` hoặc `invokeMethod` tùy **global hay object-bound**.
5. Khi cần Java typed API, dùng đúng overload `getInterface`, **check null** và kiểm thử method mappings.
6. Tách `NoSuchMethodException` khỏi `ScriptException`; không đánh đồng với thiếu engine hoặc adapter null.
7. Kiểm tra return conversion, null, primitive types và exception policy của interface.
8. Giữ lifecycle/thread-safety và bảo mật script/host access trong phạm vi provider phù hợp.

**Tài liệu chuẩn để tra cứu:**

- [Oracle Java SE 17 — `Invocable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/Invocable.html): bốn API, giá trị `null`, `NoSuchMethodException`, `ScriptException`, `IllegalArgumentException`.
- [Oracle Java SE 17 — `ScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngine.html): `eval`, `get`/`put`, scopes và context.
- [Oracle Java SE 17 — `ScriptEngineManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptEngineManager.html): engine discovery bằng provider factories và lookup theo tên/extension/MIME.
- [Oracle Java SE 17 — `AbstractScriptEngine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/AbstractScriptEngine.html): lớp nền dùng trong fixture.
- [Oracle Java SE 17 — `ScriptException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.scripting/javax/script/ScriptException.html): lỗi đánh giá/gọi script.
- [OpenJDK JEP 372 — Remove the Nashorn JavaScript Engine](https://openjdk.org/jeps/372): Nashorn được loại khỏi JDK từ Java 15; API `javax.script` vẫn tồn tại.
