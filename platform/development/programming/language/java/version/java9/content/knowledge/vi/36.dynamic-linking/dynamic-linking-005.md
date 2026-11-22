# Liên kết lại khi kiểu hoặc giả định thay đổi

Trong một hệ thống dùng `MethodHandle` và `invokedynamic`, một call site có thể được tối ưu theo kiểu đầu vào hoặc một giả định về trạng thái chương trình. Ví dụ, một lời gọi ban đầu thường nhận `String`, một receiver luôn thuộc cùng một lớp, hoặc một cấu hình hiện tại chọn một implementation cụ thể. Khi kiểu thực tế hay giả định đó thay đổi, target cũ có thể không còn phù hợp. Khi ấy runtime cần chuyển sang đường fallback, tạo target phù hợp mới và cập nhật call site.

Java cung cấp các building block cho việc này trong `java.lang.invoke`: `CallSite`, `MutableCallSite`, `VolatileCallSite`, `MethodHandle.asType()`, `SwitchPoint` và các combinator như `guardWithTest()`. Những API này không tự đoán logic relink của ứng dụng. Người thiết kế call site phải xác định giả định nào đang được cache, cách phát hiện giả định mất hiệu lực và cách xây dựng target mới.

## 1. CallSite lưu target có kiểu cố định

`CallSite` kết hợp một `MethodHandle` target với một `MethodType`. Kiểu của call site được xác định khi tạo site và không thể đổi sau đó:

```java
MethodType type = MethodType.methodType(String.class, String.class);
MutableCallSite site = new MutableCallSite(type);
```

Trong ví dụ, site nhận một `String` và trả về `String`. Mọi target được gắn vào site phải có đúng `MethodType` này. `setTarget()` không thay đổi chữ ký của site; nếu target có kiểu khác, việc gắn target thất bại với `WrongMethodTypeException`.

Đây là điểm cần phân biệt khi nói “kiểu thay đổi”: kiểu runtime của receiver hoặc dữ liệu có thể thay đổi trong khi chữ ký của call site vẫn ổn định. Nếu descriptor của chính call site cần thay đổi, phải tạo một site mới với `MethodType` mới. Một `CallSite` hiện hữu không thể đổi `type()`.

## 2. Thích nghi target bằng `MethodHandle.asType()`

Nếu site có một chữ ký ổn định nhưng implementation mới có kiểu hẹp hơn hoặc khác kiểu tham số/kết quả, có thể thử chuyển target sang đúng kiểu site bằng `asType()`.

Ví dụ, target có kiểu `(String)String`, còn site dùng chữ ký tổng quát `(Object)Object`:

```java
MethodType typedType =
        MethodType.methodType(String.class, String.class);
MethodType siteType =
        MethodType.methodType(Object.class, Object.class);

MethodHandle typedTarget = lookup.findStatic(
        Formatter.class, "render", typedType);
MethodHandle siteTarget = typedTarget.asType(siteType);
```

`asType()` tạo một handle thích nghi với chữ ký đích khi các chuyển đổi được MethodHandle hỗ trợ. Trong ví dụ, đối số `Object` được ép về `String` khi gọi và kết quả `String` được mở rộng thành `Object`. Nếu caller truyền một object không phải `String`, lời gọi có thể ném `ClassCastException` tại adapter.

`asType()` không biến mọi kiểu thành mọi kiểu khác và không thay thế kiểm tra kiểu nghiệp vụ. Nếu kiểu thực tế có nhiều dạng, hãy đặt một guard theo kiểu hoặc dùng target tổng quát có kiểm tra rõ ràng. Nếu không có chuyển đổi hợp lệ, việc tạo adapter có thể thất bại bằng `WrongMethodTypeException`.

### Chữ ký `invokedynamic` có descriptor riêng

Với bytecode `invokedynamic`, descriptor trong constant pool là chữ ký của instruction đó. Bootstrap method tạo một `CallSite` có kiểu khớp descriptor; JVM kiểm tra hợp đồng này khi liên kết. Nếu logic cần xử lý nhiều kiểu runtime, thường giữ descriptor tổng quát ổn định rồi phân nhánh/adapt target bên trong. Khi thực sự cần descriptor khác, đó là một linkage site khác, không phải đổi kiểu của site đang tồn tại.

## 3. Ba loại CallSite và cách chọn

| Loại | Target có thay đổi được không? | Cách nhìn về cập nhật |
| --- | --- | --- |
| `ConstantCallSite` | Không | Target cố định sau khi tạo |
| `MutableCallSite` | Có, qua `setTarget()` | Thread khác có thể chưa thấy target mới ngay; dùng `syncAll()` để đồng bộ việc công bố |
| `VolatileCallSite` | Có, qua `setTarget()` | Truy cập target có volatile semantics; thay đổi được công bố theo quy tắc volatile |

`ConstantCallSite` phù hợp khi target không đổi trong vòng đời site. `MutableCallSite` phù hợp khi target có thể đổi nhưng cập nhật tương đối hiếm và ứng dụng chủ động đồng bộ việc công bố. `VolatileCallSite` phù hợp khi các thread cần quan sát target mới theo semantics volatile mà không gọi `syncAll()` sau mỗi lần cập nhật.

Không chọn `MutableCallSite` rồi giả định mọi thread sẽ lập tức chạy target mới ngay sau `setTarget()`. Nếu nhiều thread có thể gọi site, hãy dùng `MutableCallSite.syncAll()` sau khi thay đổi target để công bố thay đổi theo hợp đồng API. Việc đồng bộ target không làm một lời gọi đang chạy giữa chừng bị chuyển sang implementation mới; các invocation đã bắt đầu vẫn có thể hoàn tất bằng target cũ.

## 4. Invalidating giả định bằng SwitchPoint

`SwitchPoint` biểu diễn một giả định có thể còn đúng hoặc đã bị vô hiệu hóa. Nó thường được dùng để bảo vệ một fast path được xây dựng dựa trên một điều kiện như:

- Một lớp cụ thể vẫn là implementation được chọn.
- Cấu trúc kế thừa hoặc quy tắc dispatch chưa thay đổi.
- Một cấu hình hoặc phiên bản schema vẫn còn hiệu lực.
- Một cache entry hoặc liên kết tới implementation chưa bị thay thế.

`switchPoint.guardWithTest(target, fallback)` tạo một method handle có cùng kiểu với hai handle đầu vào. Khi switch point còn hợp lệ, lời gọi đi vào `target`; sau khi switch point bị invalidated, lời gọi đi vào `fallback`.

```java
MethodHandle guarded = switchPoint.guardWithTest(fastTarget, fallbackTarget);
```

Khi giả định không còn đúng, gọi:

```java
SwitchPoint.invalidateAll(new SwitchPoint[] { switchPoint });
```

Việc invalidation là một chiều: switch point đã invalidated sẽ không trở lại trạng thái hợp lệ. Fallback có thể kiểm tra kiểu/trạng thái hiện tại, xây dựng target mới và cập nhật `MutableCallSite` để các invocation tiếp theo đi thẳng vào target mới.

## 5. Quy trình relink thường dùng

Một call site có thể tổ chức việc relink theo chu trình:

1. Bootstrap hoặc khởi tạo site, xác định `MethodType` ổn định và target ban đầu.
2. Tạo guard cho giả định đang dùng, ví dụ receiver thuộc một lớp hoặc switch point còn hợp lệ.
3. Khi giả định thay đổi, invalidation làm guard chuyển sang fallback.
4. Fallback quan sát kiểu/trạng thái hiện tại và tạo target phù hợp.
5. Fallback gọi `setTarget()` để thay target của `MutableCallSite`.
6. Gọi `MutableCallSite.syncAll()` nếu các thread khác cần thấy cập nhật.
7. Các invocation sau dùng target mới; nếu giả định lại thay đổi, hệ thống có thể cài guard hoặc switch point mới.

Fallback cần có chiến lược cho trường hợp nhiều thread cùng đi vào relink. Nếu việc xây dựng target có chi phí cao hoặc không idempotent, hãy điều phối bằng lock, atomic state hoặc một cơ chế publish duy nhất. Nếu mọi thread đều có thể cài target cùng lúc, cần bảo đảm các target được tạo từ cùng một trạng thái hợp lệ và không ghi đè nhầm một phiên bản mới hơn.

## 6. Ví dụ hoàn chỉnh: invalidation rồi relink MutableCallSite

Chương trình sau tạo một site có chữ ký `(String)String`. Ban đầu, site dùng fast path. Khi switch point bị invalidated, guard chuyển invocation đầu tiên sang fallback. Fallback cài target mới vào site và gọi `syncAll()`. Những invocation sau đi thẳng vào target mới.

Tạo tệp `DynamicRelinkDemo.java`:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.lang.invoke.SwitchPoint;

public class DynamicRelinkDemo {
    private static final MethodType TYPE =
            MethodType.methodType(String.class, String.class);
    private static final MethodHandle FAST;
    private static final MethodHandle REPLACEMENT;
    private static final MethodHandle RELINK;
    private static final MutableCallSite SITE;
    private static final SwitchPoint ASSUMPTION;

    static {
        try {
            MethodHandles.Lookup lookup = MethodHandles.lookup();
            FAST = lookup.findStatic(DynamicRelinkDemo.class, "fast", TYPE);
            REPLACEMENT = lookup.findStatic(
                    DynamicRelinkDemo.class, "replacement", TYPE);
            RELINK = lookup.findStatic(DynamicRelinkDemo.class, "relink", TYPE);
            SITE = new MutableCallSite(TYPE);
            ASSUMPTION = new SwitchPoint();
            SITE.setTarget(ASSUMPTION.guardWithTest(FAST, RELINK));
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    private static String fast(String value) {
        return "fast:" + value;
    }

    private static String replacement(String value) {
        return "new:" + value;
    }

    private static String relink(String value) throws Throwable {
        SITE.setTarget(REPLACEMENT);
        MutableCallSite.syncAll(new MutableCallSite[] { SITE });
        return (String) REPLACEMENT.invokeExact(value);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandle invoker = SITE.dynamicInvoker();

        String before = (String) invoker.invokeExact("item");
        System.out.println("Before invalidation: " + before);

        SwitchPoint.invalidateAll(new SwitchPoint[] { ASSUMPTION });

        String firstAfter = (String) invoker.invokeExact("item");
        System.out.println("First call after invalidation: " + firstAfter);

        String nextAfter = (String) invoker.invokeExact("item");
        System.out.println("Next call after relinking: " + nextAfter);
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all DynamicRelinkDemo.java
java DynamicRelinkDemo
```

Kết quả stdout:

```text
Before invalidation: fast:item
First call after invalidation: new:item
Next call after relinking: new:item
```

Lần đầu, switch point còn hợp lệ nên `FAST` được gọi. Sau `invalidateAll()`, guard chuyển sang `RELINK`. Fallback thay target của site bằng `REPLACEMENT` và gọi `syncAll()`. Invocation tiếp theo dùng target mới, không cần đi qua fallback lần nữa.

Ví dụ cố ý dùng một thread để làm rõ chu trình. Trong hệ thống nhiều thread, nhiều invocation có thể cùng chạm fallback gần thời điểm invalidation; fallback cần được thiết kế an toàn khi chạy đồng thời. Nếu target mới phụ thuộc vào trạng thái có thể tiếp tục thay đổi, hãy kiểm tra phiên bản/assumption trước khi publish target để tránh cài một target đã lỗi thời.

## 7. `MutableCallSite.syncAll()` và `VolatileCallSite`

### MutableCallSite

`setTarget()` cập nhật target của `MutableCallSite`, nhưng các thread khác có thể tiếp tục dùng target đã cache. Sau khi cập nhật một hoặc nhiều site, gọi:

```java
MutableCallSite.syncAll(new MutableCallSite[] { siteA, siteB });
```

Điều này tạo cơ chế đồng bộ để công bố target mới cho các thread theo hợp đồng của `MutableCallSite`. Có thể gom nhiều site vào một lần `syncAll()` sau khi cập nhật batch. Không cần gọi sau từng lệnh nếu các cập nhật có thể được gom lại trước khi công bố.

`syncAll()` không phải cơ chế hủy invocation đang chạy và không làm target cũ biến mất khỏi stack frame đã bắt đầu. Nó giải quyết visibility của target mới cho các invocation sau khi đồng bộ.

### VolatileCallSite

Nếu target cần được công bố với volatile semantics mỗi khi thay đổi, có thể dùng `VolatileCallSite`:

```java
VolatileCallSite site = new VolatileCallSite(type);
site.setTarget(newTarget);
```

Target của `VolatileCallSite` được đọc/ghi theo semantics volatile. Điều này thuận tiện khi nhiều thread cần quan sát target mới ngay theo quy tắc volatile, nhưng có thể tốn chi phí đồng bộ hơn so với `MutableCallSite` được cập nhật theo batch. Đo workload thực tế trước khi chọn chỉ dựa trên giả định hiệu năng.

## 8. Relink khi kiểu runtime thay đổi

Giả sử một site tổng quát nhận `Object`, nhưng có fast path riêng cho `String`. Có thể giữ `MethodType` ổn định `(Object)Object`, dùng guard để kiểm tra kiểu receiver/argument, rồi gọi target chuyên biệt khi phù hợp và fallback khi kiểu khác xuất hiện.

Về nguyên tắc:

```java
MethodType siteType =
        MethodType.methodType(Object.class, Object.class);
MethodHandle stringTarget = /* handle có kiểu (String)String */;
MethodHandle adapted = stringTarget.asType(siteType);
```

Adapter đáp ứng chữ ký call site, nhưng nó vẫn có thể ném `ClassCastException` nếu caller truyền object không tương thích. Trong một hệ thống đa kiểu, fallback nên phân loại kiểu thực tế và chọn target đúng thay vì chỉ ép tất cả về target chuyên biệt.

Nếu kiểu runtime thay đổi từ lớp A sang lớp B, một chiến lược thường dùng là guard target cho A và fallback tổng quát. Khi fallback nhận B, nó tạo target cho B và cập nhật call site. Nếu hệ thống cần hỗ trợ nhiều kiểu luân phiên, có thể xây dựng chuỗi guard hoặc cache dispatch theo kiểu; cần giới hạn kích thước cache và có chính sách invalidation.

Không nhầm kiểu runtime với `MethodType` của site. Kiểu runtime có thể thay đổi giữa các lần gọi trong khi site giữ chữ ký tổng quát ổn định. Chữ ký của site chỉ đổi khi tạo một site khác.

## 9. Bootstrap method và invokedynamic

Với `invokedynamic`, JVM gọi bootstrap method để liên kết instruction lần đầu. Bootstrap method trả về một `CallSite`; kiểu của site phải tương thích chính xác với descriptor của instruction. `CallSite.dynamicInvoker()` cung cấp method handle để thực thi target hiện tại của site.

Bootstrap có thể tạo `ConstantCallSite` nếu liên kết không đổi, `MutableCallSite` nếu runtime cần thay target, hoặc `VolatileCallSite` nếu cần visibility volatile cho cập nhật. Một bootstrap method thường chuẩn bị guard, cache hoặc fallback ngay trong lần liên kết ban đầu.

Việc thay target của `MutableCallSite` là relink ở cấp call site do ứng dụng quản lý. Nó không có nghĩa bootstrap method được gọi lại tự động mỗi khi target thay đổi. Bootstrap method được dùng để thiết lập linkage ban đầu; logic fallback tự xây dựng và publish target mới theo thiết kế.

## 10. Lỗi thường gặp

- **Cố đổi `CallSite.type()`:** kiểu site cố định từ constructor; tạo site mới nếu descriptor thực sự khác.
- **Gắn target sai kiểu:** target của `setTarget()` phải có `MethodType` đúng bằng kiểu site; dùng `asType()` khi chuyển đổi hợp lệ.
- **Cho rằng `asType()` xử lý mọi kiểu:** adapter chỉ thực hiện các chuyển đổi được MethodHandle hỗ trợ; ép kiểu runtime có thể ném `ClassCastException`.
- **Quên `syncAll()` với MutableCallSite:** thread khác có thể chưa thấy target mới; công bố sau khi cập nhật.
- **Dùng SwitchPoint như công tắc có thể bật lại:** invalidation là một chiều; tạo switch point mới cho assumption generation tiếp theo.
- **Cho rằng invalidation tự thay target:** switch point chỉ làm guard chọn fallback; fallback phải tự xây dựng và cài target mới nếu muốn relink.
- **Fallback không an toàn khi nhiều thread cùng chạy:** điều phối việc xây dựng/publish target hoặc làm fallback idempotent.
- **Không kiểm tra giả định trước khi publish:** target mới có thể đã lỗi thời nếu trạng thái thay đổi trong lúc relink.
- **Nhầm relink với dừng lời gọi cũ:** invocation đã bắt đầu bằng target cũ vẫn có thể hoàn tất.
- **Chọn VolatileCallSite hoặc MutableCallSite theo cảm tính:** quyết định theo yêu cầu visibility và đo hiệu năng thực tế.

## 11. Quy trình thiết kế relinking

1. Chọn `MethodType` ổn định cho call site; xác định kiểu runtime nào cần chuyên biệt hóa.
2. Liệt kê assumption mà fast path phụ thuộc: receiver class, class hierarchy, cấu hình, phiên bản hoặc cache entry.
3. Chọn `ConstantCallSite`, `MutableCallSite` hoặc `VolatileCallSite` theo tần suất cập nhật và yêu cầu visibility.
4. Tạo target và guard có cùng `MethodType` với site; dùng `asType()` khi adapter có ý nghĩa và an toàn.
5. Xây dựng fallback có khả năng xác định assumption hiện tại và tạo target phù hợp.
6. Khi assumption mất hiệu lực, invalidate SwitchPoint hoặc kích hoạt guard/fallback tương ứng.
7. Publish target mới bằng `setTarget()`; gọi `MutableCallSite.syncAll()` khi dùng mutable site và cần công bố cho các thread khác.
8. Điều phối nhiều fallback đồng thời và bảo vệ khỏi publish target cũ hơn trạng thái hiện tại.
9. Kiểm thử kiểu tương thích, invalidation, invocation đồng thời và việc target cũ/new target cùng tồn tại trong các invocation đang chạy.

Liên kết lại là quá trình quản lý target theo kiểu và assumption hiện tại. `CallSite` giữ chữ ký cố định; `asType()` thích nghi target khi có chuyển đổi hợp lệ; `SwitchPoint` đưa lời gọi sang fallback khi assumption bị invalidated; `MutableCallSite` hoặc `VolatileCallSite` công bố target mới theo memory semantics tương ứng. Thiết kế rõ các bước này giúp dynamic dispatch thích nghi với kiểu hoặc trạng thái thay đổi mà vẫn giữ đúng hợp đồng kiểu và visibility giữa các thread.