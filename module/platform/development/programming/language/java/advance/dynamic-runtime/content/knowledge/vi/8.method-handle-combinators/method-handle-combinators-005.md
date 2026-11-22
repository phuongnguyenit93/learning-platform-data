# 8.5 Phân biệt `collectArguments` với `foldArguments` qua luồng dữ liệu

Hai combinator `java.lang.invoke.MethodHandles.collectArguments` và `MethodHandles.foldArguments` đều xây dựng một `MethodHandle` mới bằng cách **chạy một handle xử lý trước**, rồi mới gọi `target`. Cả hai đều có thể biến đầu ra của bước xử lý thành đối số của `target`, nhưng khác nhau ở điểm quyết định: **đầu vào cho bước xử lý có được chuyển tiếp nguyên vẹn tới `target` hay không**.

- **`collectArguments`:** `filter` xử lý một nhóm đối số **riêng**; nhóm này được **thay thế** bằng kết quả của filter khi gọi target. Những đối số filter nhận không tự động đi tiếp tới target.
- **`foldArguments`:** `combiner` xử lý một nhóm đối số được **dùng chung với target**. Kết quả của combiner được **chèn trước nhóm đối số đó** khi gọi target; chính các đối số gốc vẫn đi tiếp.

Đây là nội dung cốt lõi của bài. Hãy đọc chữ ký `MethodType` và đường đi của **từng giá trị** thay vì chỉ nhìn kết quả cuối, vì nhiều ví dụ đơn giản cho ra cùng kết quả dù cấu trúc gọi khác nhau.

Bài sử dụng **Java 17+**. Các hàm được trình bày nằm trong `java.lang.invoke.MethodHandles`; `MethodHandle` là một tham chiếu có kiểu đến khả năng gọi method/constructor/field hoặc một chuỗi combinator.

## 1. Bốn khái niệm cần biết trước

| Thuật ngữ | Vai trò |
| --- | --- |
| `target` | Handle sẽ được gọi **sau cùng**, nhận đầu vào cuối cùng và quyết định kiểu trả về của adapter |
| `filter` của `collectArguments` | Xử lý tập đối số riêng, có thể trả về **một giá trị** để thay một vị trí đối số của target |
| `combiner` của `foldArguments` | Xử lý một số đối số **đồng thời được chuyển tiếp cho target**, có thể trả về một giá trị bổ sung |
| `pos` | Vị trí bắt đầu trong danh sách tham số; đánh số từ **0**, tính trên kiểu của `target` |

Cả hai combinator **tạo handle mới**; việc tạo adapter chưa gọi filter, combiner hoặc target. Chúng thực thi khi adapter được gọi. Khi xử lý trước ném exception, target sẽ **không được gọi** trong lượt đó. Trình tự bình thường là *preprocess trước, target sau*, không phải target rồi mới lọc giá trị trả về.

Phân biệt thêm: `filterReturnValue` xử lý **kết quả của target**, còn hai combinator đang học xử lý **đầu vào trước khi gọi target**. `asCollector` dùng để đóng gói nhiều đối số thành mảng, cũng khác `collectArguments`.

## 2. Nhìn cùng một target và cùng một filter

Đặt hai method Java có kiểu:

~~~java
static String prepare(String a, String b) {
    return "<" + a + "+" + b + ">";
}

static String target(String merged, String left, String right) {
    return merged + " | " + left + " | " + right;
}
~~~

Đây là **hai method minh họa**, chưa phải chương trình độc lập. Khi dùng `MethodHandles.Lookup.findStatic` để lấy handle:

~~~text
prepare.type() = (String,String)String
target.type()  = (String,String,String)String
~~~

Xét `A`, `B`, `C`, `D` là **bốn chuỗi đầu vào khác nhau**. Nếu muốn `prepare(A,B)` tạo chuỗi `<A+B>` rồi truyền `C,D` vào hai tham số còn lại của target, dùng `collectArguments`. Nếu muốn target nhận **lại chính `A,B`**, bên cạnh `<A+B>`, dùng `foldArguments`.

### 2.1. Luồng dữ liệu của `collectArguments`

~~~java
MethodHandle collected = MethodHandles.collectArguments(targetHandle, 0, prepareHandle);
~~~

Luồng gọi:

~~~text
caller: collected(A, B, C, D)
             │  │  │  │
             └──┘  │  │
                │   │  │
       prepare(A, B) │  │
                │    │  │
             "<A+B>" │  │
                └────┴──┘
                      │
              target("<A+B>", C, D)
                      │
                "<A+B> | C | D"
~~~

`prepare` nhận `A,B`; `target` chỉ nhận **kết quả** `<A+B>` và hai đối số **khác** là `C,D`. Adapter phải nhận **bốn** tham số:

~~~text
targetHandle.type() = (String,String,String)String
prepareHandle.type()= (String,String)String
collected.type()    = (String,String,String,String)String
~~~

Cụ thể, vị trí 0 của target vốn là `merged` kiểu `String`; `collectArguments` **thay một tham số** `merged` bằng **hai tham số** `a,b` cần để chạy filter. Sau khi filter trả về `String`, target nhận lại ba đối số đúng kiểu của nó.

### 2.2. Luồng dữ liệu của `foldArguments`

~~~java
MethodHandle folded = MethodHandles.foldArguments(targetHandle, prepareHandle);
~~~

Luồng gọi:

~~~text
caller: folded(A, B)
              │  │
              ├──┤
              │  └─────┐
              ▼        │
       prepare(A, B)   │
              │        │
           "<A+B>"     │
              │        │
              └──┐     │
                 ▼     ▼
          target("<A+B>", A, B)
                 │
            "<A+B> | A | B"
~~~

Adapter nhận **chỉ hai đối số** `A,B`. Chúng được dùng **hai lần theo luồng dữ liệu**: gửi vào `prepare` trước, rồi được chuyển tiếp nguyên vẹn sang `target` bên cạnh kết quả `<A+B>`.

~~~text
targetHandle.type() = (String,String,String)String
prepareHandle.type()= (String,String)String
folded.type()       = (String,String)String
~~~

Từ `target(merged,left,right)`, `foldArguments` khiến giá trị `merged` được **tính từ** `left,right`. Call site không phải cung cấp thêm `merged`.

### 2.3. Bảng so sánh trực tiếp

| Điểm so sánh | `collectArguments(target,0,filter)` | `foldArguments(target,combiner)` |
| --- | --- | --- |
| Handle xử lý trước | `filter(String,String) -> String` | `combiner(String,String) -> String` |
| Adapter nhận gì? | `A,B,C,D` | `A,B` |
| Giá trị trả về của bước trước | `<A+B>` | `<A+B>` |
| Target nhận gì? | `target(<A+B>,C,D)` | `target(<A+B>,A,B)` |
| Có gửi tiếp chính đầu vào bước trước vào target? | **Không**, trừ khi thiết kế riêng các đối số khác mang cùng giá trị | **Có**, theo hợp đồng kiểu của fold |
| Số đối số của adapter | 4 | 2 |
| Kết quả minh họa | `<A+B> | C | D` | `<A+B> | A | B` |

Hai handle vẫn có **kiểu trả về giống target**; sự khác nhau nằm ở **đầu vào adapter** và cách chuyển tiếp đối số.

## 3. Quy tắc tổng quát khi `filter`/`combiner` có kết quả

Ký hiệu `T` là kiểu trả về của target, `V` là kiểu giá trị trung gian, `P...` là các tham số phía trước, `A...` là tham số của hàm xử lý trước, `S...` là các tham số còn lại.

**`collectArguments(target, pos, filter)`:**

~~~text
target(P..., V, S...) -> T
filter(A...)         -> V

adapter(P..., A..., S...) -> T:
    v = filter(A...)
    return target(P..., v, S...)
~~~

Filter lấy **nhóm đối số mới của adapter tại `pos`**, thay cho một đối số kiểu `V` của target. `A...` **không còn** trong lời gọi target, trừ khi những vị trí khác của adapter mang lại cùng giá trị.

**`foldArguments(target, pos, combiner)`:**

~~~text
target(P..., V, A..., S...) -> T
combiner(A...)             -> V

adapter(P..., A..., S...) -> T:
    v = combiner(A...)
    return target(P..., v, A..., S...)
~~~

Combiner tính `v` từ **chính nhóm `A...` vẫn được dùng bởi target**. Nhóm `A...` không bị mất sau bước xử lý.

Cả hai đều yêu cầu `V` **trùng chính xác** với kiểu đối số target ở `pos`. Các kiểu tham số tương ứng của combiner/fold cũng phải khớp chính xác với các vị trí mà nó dùng. Combinator **không tự chạy `asType`** để chữa sai kiểu. Cấu trúc không hợp lệ thường ném `IllegalArgumentException` **ngay khi tạo adapter**.

### 3.1. Công thức số lượng tham số

Gọi `N` là số tham số của target và `M` là số tham số của filter/combiner.

| Bước xử lý trước | `collectArguments` | `foldArguments` |
| --- | --- | --- |
| Có trả về giá trị (khác `void`) | Adapter có `N - 1 + M` tham số | Adapter có `N - 1` tham số |
| Trả về `void` | Adapter có `N + M` tham số | Adapter có **`N`** tham số |

`foldArguments` với kết quả khác `void` thường không thay tổng số tham số theo `M`: nó bỏ một tham số của target vì tham số ấy đã được combiner tính ra, còn nhóm tham số nguồn `A...` vốn đã thuộc target.

Đây là công thức về **chữ ký**, không mô tả số đối tượng được tạo hoặc chi phí thực thi. Hiệu năng thực tế phụ thuộc target, combiner, JIT và hoàn cảnh chạy.

## 4. `pos` khác 0: nhìn dòng dữ liệu để tránh nhầm

Xét target khác:

~~~java
static String withPrefix(String prefix, String merged,
                         String left, String right) {
    return prefix + ": " + merged + " | " + left + " | " + right;
}
~~~

Handle target có kiểu `(String,String,String,String)String`. Chọn `pos = 1`: kiểu `String merged` là vị trí được chèn/thay bằng kết quả xử lý, trong khi `prefix` là tham số ở **trước** vị trí đó.

~~~java
MethodHandle collectAt1 =
        MethodHandles.collectArguments(prefixTarget, 1, prepareHandle);
MethodHandle foldAt1 =
        MethodHandles.foldArguments(prefixTarget, 1, prepareHandle);
~~~

Hai kết quả:

~~~text
collectAt1.type() = (String,String,String,String,String)String
foldAt1.type()    = (String,String,String)String
~~~

Lời gọi và đường đi của giá trị:

~~~text
collectAt1("P", "A", "B", "C", "D")
  prepare("A","B") -> "<A+B>"
  withPrefix("P","<A+B>","C","D")
  => "P: <A+B> | C | D"

foldAt1("P", "A", "B")
  prepare("A","B") -> "<A+B>"
  withPrefix("P","<A+B>","A","B")
  => "P: <A+B> | A | B"
~~~

Trong `foldAt1`, `pos=1` không phải là vị trí của đối số đầu tiên truyền vào `prepare` trong lời gọi cuối cùng theo một cách tùy ý: vị trí đó xác định **điểm chèn kết quả** vào chữ ký target; các tham số liền sau kiểu `V` phải khớp với đầu vào combiner. Với `collectAt1`, hai đầu vào filter nằm tại vị trí 1 và 2 của **adapter**, rồi được thay bằng một kết quả tại vị trí 1 của target.

Với `foldArguments(target, combiner)` không có tham số `pos`, Java hiểu ngầm là `pos = 0`.

## 5. Trường hợp xử lý trước trả về `void`

Khi `filter` hoặc `combiner` không trả kết quả, **không có giá trị nào chèn vào target**. Tuy nhiên cách truyền đối số vẫn khác nhau rõ ràng. Đây là trường hợp phổ biến với logging, tracing hoặc audit.

Cho:

~~~java
static void audit(String a, String b) {
    System.out.println("audit(" + a + "," + b + ")");
}

static String pair(String a, String b) {
    return a + "/" + b;
}
~~~

Với `pairHandle.type() == (String,String)String` và `auditHandle.type() == (String,String)void`:

~~~java
MethodHandle collectedAudit =
        MethodHandles.collectArguments(pairHandle, 0, auditHandle);
MethodHandle foldedAudit =
        MethodHandles.foldArguments(pairHandle, auditHandle);
~~~

**`collectArguments` với filter void:**

~~~text
collectedAudit("auditA","auditB","A","B")
  audit("auditA","auditB")  // đối số CHỈ dành cho audit
  pair("A","B")             // hai đối số KHÁC
  => "A/B"

type: (String,String,String,String)String
~~~

**`foldArguments` với combiner void:**

~~~text
foldedAudit("A","B")
  audit("A","B")  // xem chính những giá trị target sẽ nhận
  pair("A","B")
  => "A/B"

type: (String,String)String
~~~

Chọn **fold void** để ghi log/kiểm tra các giá trị sắp được target sử dụng mà **không yêu cầu caller đưa một bộ tham số bổ sung**. Chọn **collect void** khi tác vụ xử lý trước cần **một bộ đầu vào tách biệt**, chẳng hạn thông tin audit riêng không truyền vào target.

Đừng hiểu `void` là “không có thay đổi gì”: tác dụng phụ của hàm audit, nếu có, vẫn xảy ra trước lời gọi target. Nếu audit ném exception, target không chạy.

## 6. Chương trình Java 17 chạy hoàn chỉnh

Tạo file **`CollectFoldDemo.java`** với nội dung sau. Tất cả method `static` nằm trong cùng class nên `MethodHandles.lookup().findStatic` có thể lấy handle của chúng.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public final class CollectFoldDemo {
    static String prepare(String a, String b) {
        System.out.println("  prepare(" + a + "," + b + ")");
        return "<" + a + "+" + b + ">";
    }

    static String target(String merged, String left, String right) {
        System.out.println("  target(" + merged + "," + left + "," + right + ")");
        return merged + " | " + left + " | " + right;
    }

    static String withPrefix(String prefix, String merged, String left, String right) {
        System.out.println("  withPrefix(" + prefix + "," + merged + "," + left + "," + right + ")");
        return prefix + ": " + merged + " | " + left + " | " + right;
    }

    static void audit(String a, String b) {
        System.out.println("  audit(" + a + "," + b + ")");
    }

    static String pair(String a, String b) {
        System.out.println("  pair(" + a + "," + b + ")");
        return a + "/" + b;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle filter = lookup.findStatic(CollectFoldDemo.class, "prepare",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle render = lookup.findStatic(CollectFoldDemo.class, "target",
                MethodType.methodType(String.class, String.class, String.class, String.class));
        MethodHandle collect = MethodHandles.collectArguments(render, 0, filter);
        MethodHandle fold = MethodHandles.foldArguments(render, filter);

        System.out.println("render: " + render.type());
        System.out.println("filter: " + filter.type());
        System.out.println("collect: " + collect.type());
        System.out.println("fold: " + fold.type());

        System.out.println("collect call:");
        String collected = (String) collect.invokeExact("A", "B", "C", "D");
        System.out.println("collect result: " + collected);

        System.out.println("fold call:");
        String folded = (String) fold.invokeExact("A", "B");
        System.out.println("fold result: " + folded);

        MethodHandle prefixTarget = lookup.findStatic(CollectFoldDemo.class, "withPrefix",
                MethodType.methodType(String.class, String.class, String.class, String.class, String.class));
        MethodHandle collectAt1 = MethodHandles.collectArguments(prefixTarget, 1, filter);
        MethodHandle foldAt1 = MethodHandles.foldArguments(prefixTarget, 1, filter);
        System.out.println("collect at pos=1: " + collectAt1.type());
        System.out.println("fold at pos=1: " + foldAt1.type());
        System.out.println("collect pos1 call:");
        System.out.println("collect pos1 result: " + (String) collectAt1.invokeExact("P", "A", "B", "C", "D"));
        System.out.println("fold pos1 call:");
        System.out.println("fold pos1 result: " + (String) foldAt1.invokeExact("P", "A", "B"));

        MethodHandle logger = lookup.findStatic(CollectFoldDemo.class, "audit",
                MethodType.methodType(void.class, String.class, String.class));
        MethodHandle pair = lookup.findStatic(CollectFoldDemo.class, "pair",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle collectVoid = MethodHandles.collectArguments(pair, 0, logger);
        MethodHandle foldVoid = MethodHandles.foldArguments(pair, logger);
        System.out.println("collect void: " + collectVoid.type());
        System.out.println("fold void: " + foldVoid.type());
        System.out.println("collect void call:");
        System.out.println("collect void result: "
                + (String) collectVoid.invokeExact("auditA", "auditB", "A", "B"));
        System.out.println("fold void call:");
        System.out.println("fold void result: " + (String) foldVoid.invokeExact("A", "B"));

        try {
            MethodHandles.collectArguments(render, 0, MethodHandles.identity(int.class));
            throw new AssertionError("expected incompatible filter");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad collect shape: " + expected.getClass().getSimpleName());
        }
        try {
            MethodHandles.foldArguments(render, MethodHandles.identity(int.class));
            throw new AssertionError("expected incompatible combiner");
        } catch (IllegalArgumentException expected) {
            System.out.println("bad fold shape: " + expected.getClass().getSimpleName());
        }
        try {
            String ignored = (String) fold.invokeExact("A", "B", "C");
            throw new AssertionError("expected wrong invocation");
        } catch (WrongMethodTypeException expected) {
            System.out.println("bad invoke type: " + expected.getClass().getSimpleName());
        }
    }
}
~~~

Chạy từ thư mục chứa file bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 CollectFoldDemo.java
java CollectFoldDemo
~~~

**Stdout chính xác** (các dòng có hai khoảng trắng đầu dòng biểu thị lời gọi bên trong `prepare`/`target`/`audit`/`pair`):

~~~text
render: (String,String,String)String
filter: (String,String)String
collect: (String,String,String,String)String
fold: (String,String)String
collect call:
  prepare(A,B)
  target(<A+B>,C,D)
collect result: <A+B> | C | D
fold call:
  prepare(A,B)
  target(<A+B>,A,B)
fold result: <A+B> | A | B
collect at pos=1: (String,String,String,String,String)String
fold at pos=1: (String,String,String)String
collect pos1 call:
  prepare(A,B)
  withPrefix(P,<A+B>,C,D)
collect pos1 result: P: <A+B> | C | D
fold pos1 call:
  prepare(A,B)
  withPrefix(P,<A+B>,A,B)
fold pos1 result: P: <A+B> | A | B
collect void: (String,String,String,String)String
fold void: (String,String)String
collect void call:
  audit(auditA,auditB)
  pair(A,B)
collect void result: A/B
fold void call:
  audit(A,B)
  pair(A,B)
fold void result: A/B
bad collect shape: IllegalArgumentException
bad fold shape: IllegalArgumentException
bad invoke type: WrongMethodTypeException
~~~

Các dòng `bad ... shape` xảy ra **khi xây adapter**: `identity(int)` có kiểu trả về `int`, nhưng target đang cần `String` ở vị trí thay/chèn, nên combinator từ chối cấu trúc bằng `IllegalArgumentException`. Dòng `bad invoke type` khác bản chất: adapter `fold` được tạo hợp lệ, nhưng caller cố gọi `invokeExact` với ba tham số thay vì hai, dẫn tới `WrongMethodTypeException`. Khi debug, xác định lỗi tại **bước tạo handle** hay **bước gọi handle**.

Đoạn code bắt `Throwable` ở `main` vì `invokeExact` khai báo `throws Throwable`. Trong phần mềm thực tế, xử lý lỗi dựa vào hợp đồng nghiệp vụ và không nuốt các lỗi bất ngờ chỉ để ứng dụng tiếp tục.

## 7. Cách chọn đúng combinator trong ứng dụng

**Khi bạn muốn chuyển đổi nhiều đầu vào thành một đối số cho target**, dùng `collectArguments`. Ví dụ adapter nhận `(String amountText, String currency, OrderContext ctx)`; filter biến cặp amount/currency thành một đối tượng `Money`, rồi target chỉ cần `(Money, OrderContext)`. Filter nhận **hai đối số đầu** và thay thế vị trí `Money` mà target cần. `OrderContext` không được filter tự động nhận hay sao chép.

**Khi target vẫn cần các đầu vào gốc song song với kết quả suy ra từ chúng**, dùng `foldArguments`. Ví dụ target nhận `(Signature signature, byte[] payload, Key key)`, combiner nhận `(byte[] payload, Key key)` để tính chữ ký. Adapter chỉ yêu cầu `(payload, key)`, tính `signature` rồi gọi target với **chữ ký cộng dữ liệu gốc**. Kiểu `Signature` ở đây chỉ minh họa miền nghiệp vụ; không có nghĩa mọi thuật toán ký có thể biểu diễn bằng một bước đồng bộ giản đơn.

**Khi cần kiểm tra/log tham số trước khi target xử lý**, `foldArguments` với combiner `void` có thể chia sẻ nhóm tham số với target. Nếu bộ tham số dành cho logger hoàn toàn **riêng** so với tham số target, `collectArguments` với filter `void` phù hợp hơn.

**Nếu chỉ cần biến đổi một tham số riêng lẻ**, `filterArguments(target,pos,filter)` thường biểu đạt ý định ngắn hơn: một unary filter thay một đối số của target; trường hợp này tương đương một `collectArguments` với filter nhận một đối số và trả một giá trị tương ứng. Khi filter nhận **nhiều** đối số để tính một giá trị, `collectArguments` cho thấy rõ việc thay thế một đoạn đối số.

**Nếu cần đổi thứ tự đối số** để các kiểu khớp, combinator này không tự permute: dùng `permuteArguments` (và có thể `dropArguments` hoặc `insertArguments`) một cách rõ ràng, rồi so sánh `type()` ở từng bước.

## 8. Những giới hạn và lỗi thường gặp

| Sai lầm | Hệ quả / cách sửa |
| --- | --- |
| Chọn `collectArguments` nhưng nghĩ filter input cũng đi vào target | Chữ ký adapter có nhóm tham số riêng; target chỉ nhận **kết quả filter** và các tham số còn lại. Nếu muốn tái sử dụng input, xét `foldArguments`. |
| Chọn `foldArguments` với target không có nhóm tham số trùng kiểu đầu vào combiner | Xây adapter thất bại (`IllegalArgumentException`). Đọc `target.type()` và `combiner.type()`. |
| Nhầm `pos` là index của method nguồn hoặc index class | `pos` là **index 0-based trong danh sách tham số của target**, liên quan trực tiếp vị trí thay/chèn. |
| Cho rằng `foldArguments` luôn tạo thêm tham số để truyền vào combiner | Combiner tái sử dụng tham số target; adapter thường ít hơn một tham số nếu combiner trả giá trị. |
| Nghĩ combiner `void` trong fold bỏ qua tham số target | Không. Nó chạy trước; cùng các tham số ấy vẫn đi vào target. |
| Nghĩ filter `void` trong collect thay một tham số target | Không có kết quả để thay; adapter chỉ **chèn** thêm các tham số dành riêng cho filter. |
| Cấu trúc adapter sai và kiểu gọi adapter sai là cùng loại lỗi | Sai cấu trúc thường là `IllegalArgumentException` lúc ghép; gọi `invokeExact` sai descriptor là `WrongMethodTypeException` lúc chạy. |
| Nhầm `collectArguments` với `filterReturnValue` | Collect xử lý **đối số trước target**; filterReturnValue xử lý **kết quả sau target**. |
| Cho rằng cùng tên kiểu nghĩa là compatible dù khác class loader | `MethodType` dùng `Class<?>` thật sự; phải đối chiếu kiểu Java chính xác, không dựa vào tên in ra. |
| Dùng `invokeExact` mà không xét kiểu trả về của call site | Cả tham số lẫn kiểu trả về phải khớp chính xác; thường in `adapter.type()` và ép kiểu trả về có chủ ý. |

Khi làm việc với nhiều combinator liên tiếp, hãy in kiểu sau từng bước:

~~~java
System.out.println(filter.type());
System.out.println(targetHandle.type());
System.out.println(adapter.type());
~~~

Các dòng trên là **gợi ý chẩn đoán**, không phải chương trình độc lập. Một `MethodHandle` có thể đại diện cho method instance (có tham số receiver), handle đã bind tham số hoặc nhiều adapter lồng nhau. Bởi vậy không đoán số đối số từ chữ ký method Java ban đầu sau khi đã qua các phép biến đổi; hãy tin `type()` của handle hiện tại.

## 9. Tự kiểm tra luồng dữ liệu

Giả sử `target(String result, String x, String y)` và `combine(String x,String y) -> String` đều đã có handle với đúng những kiểu trên.

1. `collectArguments(target,0,combine)` có kiểu adapter nào? Với đầu vào `("A","B","C","D")`, target nhận gì?
2. `foldArguments(target,combine)` có kiểu adapter nào? Với đầu vào `("A","B")`, target nhận gì?
3. Thay combiner bằng `audit(String,String) -> void`, còn target đổi thành `pair(String,String) -> String`. Adapter `collectArguments(pair,0,audit)` và `foldArguments(pair,audit)` khác nhau thế nào?
4. Khi `combine` trả `int` nhưng target yêu cầu `String` ở vị trí cần thay/chèn, lỗi phát sinh lúc nào? Khi adapter hợp lệ nhưng gọi `invokeExact` với số đối số không khớp thì sao?

**Đáp án:** (1) `(String,String,String,String)String`, target nhận `(combine("A","B"),"C","D")`; (2) `(String,String)String`, target nhận `(combine("A","B"),"A","B")`; (3) collect void thêm **hai đối số riêng dành cho audit**, fold void dùng **chính hai đối số target nhận**; (4) cấu trúc không hợp lệ gây `IllegalArgumentException` khi tạo adapter, kiểu gọi `invokeExact` không khớp gây `WrongMethodTypeException` lúc gọi.

**Tài liệu chuẩn:** [`MethodHandles.collectArguments` / `foldArguments` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html), [`MethodHandle.invokeExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html) và [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html).