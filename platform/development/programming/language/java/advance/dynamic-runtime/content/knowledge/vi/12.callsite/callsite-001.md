# 12.1 CallSite là nơi giữ target và được ràng buộc bởi một MethodType

**Module:** Java Advance - dynamic-runtime  
**Nhóm kiến thức:** 12. CallSite  
**Môi trường thực hành:** Java 17 trở lên.

## Mục tiêu học tập

Trong `java.lang.invoke`, `CallSite` đại diện cho **trạng thái liên kết của một điểm gọi động**. Đối tượng này giữ một `MethodHandle` gọi là **target**, đồng thời giữ một **`MethodType` cố định**. Nếu `CallSite` cho phép thay target, target mới vẫn phải có đúng kiểu đó; thay đổi phần triển khai không được thay đổi hợp đồng gọi của call site.

Sau bài này, bạn có thể:

1. Phân biệt **`CallSite`**, **`MethodHandle`**, **`MethodType`**, **`dynamicInvoker()`** và **instruction `invokedynamic`**.
2. Giải thích bất biến `site.type().equals(site.getTarget().type())` cùng cơ chế kiểm tra của `setTarget(...)`.
3. Nhận biết hành vi của `ConstantCallSite`, `MutableCallSite` và `VolatileCallSite`; chọn chúng theo nhu cầu thay đổi liên kết và khả năng nhìn thấy cập nhật giữa các thread.
4. Biết vì sao `getTarget()` tạo snapshot của một target tại thời điểm đọc, còn handle trả bởi `dynamicInvoker()` tiếp tục chuyển tiếp đến target của site.
5. Biên dịch Java 17+, quan sát thay target, lỗi `WrongMethodTypeException`, target chưa khởi tạo, và thích nghi `MethodHandle.asType(...)`.
6. Hiểu quan hệ với bootstrap method của `invokedynamic` mà không nhầm **tự tạo `CallSite` trong Java code** với **việc JVM phát sinh instruction `invokedynamic`**.

## 1. Ba lớp ý nghĩa: nơi gọi, target và kiểu

Hãy hình dung một hệ thống có một điểm gọi logic tên `transform`. Ban đầu nó chuyển chuỗi thành chữ hoa; về sau router quyết định chuyển sang chữ thường. **Thư viện muốn thay cách làm, không muốn bắt caller đổi số lượng/kiểu đối số hoặc kiểu trả về.**

~~~text
Caller: truyền String, kỳ vọng String
               |
               v
       CallSite type = (String)String  <----- KHÔNG THAY ĐỔI
               |
               | target hiện tại (MethodHandle)
               v
        upper(String):String           <-- có thể đổi
               |
        sau khi relink
               v
        lower(String):String           <-- cùng MethodType
~~~

Các thành phần:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `MethodHandle` | Một tham chiếu thực thi được và có kiểu đến method, constructor, field operation, hoặc chuỗi adapter | Handle trỏ đến `upper(String)String` |
| `MethodType` | Hợp đồng **kiểu trả về và danh sách kiểu tham số theo thứ tự**; không chứa tên method hay danh tính target | `(String)String` |
| `CallSite` | Nơi giữ target; biểu diễn một trạng thái liên kết có **kiểu cố định** | Một `MutableCallSite` ban đầu trỏ `upper`, sau trỏ `lower` |
| `CallSite.getTarget()` | Đọc handle hiện tại theo quy tắc memory của từng loại site | Trước cập nhật: `upperHandle` |
| `CallSite.dynamicInvoker()` | Tạo handle có cùng kiểu với site, luôn chuyển tiếp qua **target đang có của site** | Invoker duy trì đường gọi qua `CallSite` |
| `invokedynamic` | Instruction bytecode mà JVM liên kết tới một `CallSite` qua bootstrap method | Call site dành cho một điểm gọi ký hiệu trong constant pool |

**Điểm chính:** `CallSite` không phải “một method có thể thay tham số tùy thích”. Nó là **một điểm liên kết linh hoạt về đích đến nhưng cố định về kiểu**. `MethodHandle` không có tên source bắt buộc; tên `upper`, `lower` chỉ giúp ví dụ dễ đọc.

### 1.1. `MethodType` bao gồm những gì?

~~~java
MethodType contract =
        MethodType.methodType(String.class, String.class);
~~~

Đoạn minh họa này tạo **`(String)String`**: **tham số thứ nhất** của `methodType` là **return type**, các tham số tiếp theo là **parameter types** của handle. Nếu có hai đối số:

~~~java
MethodType arithmetic =
        MethodType.methodType(int.class, int.class, int.class);
~~~

thì nó biểu diễn **`(int,int)int`**, không phải chỉ một kiểu `int`.

`MethodType` không chứa **tên method**, **tên biến tham số**, annotation, thông tin quyền truy cập, object receiver đang bind, hay logic nghiệp vụ. Nó đại diện cho **chữ ký runtime** mà caller và target phải hiểu như nhau.

**Với method instance** như `String.length()`, một handle thu được bằng `Lookup.findVirtual` thường mang thêm **receiver** làm parameter đầu của `MethodType`, ví dụ `(String)int`. Với static method, không có receiver target ẩn. Vì vậy phải lấy `handle.type()` thực tế, đừng đoán từ số lượng tham số source.

## 2. Bất biến quan trọng nhất: `CallSite.type()` không đổi

Java 17 mô tả:

- `site.type()` trả `MethodType` của target hiện tại.
- Giá trị **type về mặt ngữ nghĩa là bất biến** trong suốt vòng đời của site.
- Nếu type của target có thể thay đổi, mọi call site sử dụng descriptor cố định đã được liên kết sẽ trở nên không an toàn. Do đó `setTarget(newTarget)` **từ chối** handle có kiểu không bằng type đã cố định.

Ta có thể diễn đạt:

~~~text
T = site.type()                              // cố định
site.getTarget().type().equals(T) == true  // luôn giữ khi site hợp lệ

newTarget.type().equals(T) == true         // điều kiện của setTarget
~~~

Đây là **biểu thức logic minh họa**, không phải một file Java chạy độc lập. Khi target được đổi thành công, **danh tính handle** hoặc **logic bên trong** có thể khác, nhưng `MethodType` tại interface của site phải giống.

### 2.1. `equals` là so sánh đúng, không phải “gần giống”

Giả sử site có type `(String)String`:

| Target dự kiến | `MethodType` | `setTarget` |
| --- | --- | --- |
| `String upper(String)` | `(String)String` | Hợp lệ |
| `String lower(String)` | `(String)String` | Hợp lệ |
| `Object wrap(Object)` | `(Object)Object` | Không hợp lệ nếu dùng trực tiếp |
| `String noArg()` | `()String` | Không hợp lệ, thiếu tham số |
| `Object wrap(Object).asType((String)String)` | `(String)String` | Có thể hợp lệ sau khi tạo adapter |
| Handle kiểu `(String)Object` | `(String)Object` | Không hợp lệ vì return type khác |

Ngay cả `String` là subtype của `Object`, **`(String)String` không bằng `(Object)Object`**. `CallSite.setTarget` không tự động nâng kiểu tham số, boxing, hay chèn cast như một adapter. Nếu cần, bạn phải **thích nghi handle trước** bằng `asType` hoặc một combinator phù hợp rồi mới giao nó cho site.

Mặt khác, việc hai target có cùng `MethodType` không có nghĩa chúng có cùng semantics, quyền phụ trợ, độ an toàn thread hoặc side effects. Kiểu là **hợp đồng gọi tối thiểu**, không phải mô hình bảo mật hoặc quy ước hành vi đầy đủ.

### 2.2. Khi thay target sai kiểu

Các site có thể thay target như `MutableCallSite` và `VolatileCallSite` ném `WrongMethodTypeException` nếu `newTarget.type()` không bằng type hiện tại. Truyền `null` ném `NullPointerException`. Riêng `ConstantCallSite` là bất biến về target, nên lời gọi `setTarget(...)` luôn ném `UnsupportedOperationException`, kể cả khi bạn định đặt một handle cùng kiểu.

**Thời điểm phát hiện lỗi:** Với mutable/volatile site, type mismatch bị chặn **ngay lúc `setTarget`**, không phải đợi người dùng gọi `dynamicInvoker()` mới biết. Điều này giữ cho tất cả caller đã biên dịch theo type cũ không phải xử lý một chữ ký hoàn toàn mới giữa chừng.

## 3. Ba loại CallSite trong Java SE 17

| Loại | Target có đổi được? | Ngữ nghĩa visibility | Tình huống dùng |
| --- | --- | --- | --- |
| `ConstantCallSite` | **Không**, được cố định ngay từ lúc tạo | Target như trường `final`; `dynamicInvoker()` có thể trả luôn permanent target | Liên kết đã biết, không cần hot swap |
| `MutableCallSite` | **Có**, nếu target mới cùng type | Đọc/ghi target theo ngữ nghĩa trường **thông thường**, không tự ép thread khác thấy ngay | Tối ưu dynamic dispatch; cập nhật được điều phối với `syncAll` khi cần |
| `VolatileCallSite` | **Có**, nếu cùng type | Đọc/ghi target có ngữ nghĩa tương tự **volatile field** | Cần quan sát cập nhật giữa thread sớm và chắc chắn hơn |

`CallSite` bản thân là abstract class; trong Java 17 các lớp trực tiếp được dùng phổ biến là ba loại trên. Chúng giải quyết **cơ chế liên kết**, không tự thực thi các yêu cầu đồng bộ nghiệp vụ, transaction hay phân quyền.

### 3.1. `ConstantCallSite`: một lần gắn, giữ nguyên

~~~java
ConstantCallSite site = new ConstantCallSite(upperHandle);
MethodHandle invoker = site.dynamicInvoker();
~~~

Đây là đoạn Java **giả định biến `upperHandle` đã tồn tại**. Constructor lấy kiểu cố định từ `upperHandle.type()`. `getTarget()` luôn trỏ cùng permanent handle, và `dynamicInvoker()` trả permanent target tương ứng. Nếu thử `site.setTarget(lowerHandle)`, ném `UnsupportedOperationException`.

Một ứng dụng còn có thể dùng constructor `ConstantCallSite(MethodType, MethodHandle createTargetHook)` được bảo vệ (`protected`) cho trường hợp tạo target phức tạp trong subclass; không cần dùng constructor đặc biệt này để hiểu bất biến trong bài. Điểm chính: **không phải site nào cũng có thể relink**.

### 3.2. `MutableCallSite`: thay target nhưng không thay type

Hai cách tạo:

~~~java
MutableCallSite siteA = new MutableCallSite(
        MethodType.methodType(String.class, String.class));
MutableCallSite siteB = new MutableCallSite(upperHandle);
~~~

- `siteA` đã có type `(String)String` **ngay từ constructor**, dù chưa được gán target nghiệp vụ. Target mặc định của nó là một handle **cùng type nhưng ném `IllegalStateException` khi gọi**.
- `siteB` lấy type và target ban đầu từ `upperHandle`.
- Cả hai sau đó chỉ chấp nhận `setTarget(...)` với handle kiểu `(String)String`.

Với ứng dụng đơn luồng, gọi `setTarget` rồi gọi `dynamicInvoker` dễ thấy target mới. Với **đa luồng**, `MutableCallSite` cố ý có tính chất như trường thường: thread khác có thể dùng lại target đã cache; không được giả định thay đổi hiển thị tức thì. `MutableCallSite.syncAll(new MutableCallSite[]{site})` cung cấp ranh giới đồng bộ hóa cập nhật.

**Không lạm dụng `syncAll`:** nó có chi phí; đồng bộ theo nhóm khi hợp lý, và tránh concurrent updates không được điều phối. Nó không đảo ngược lời gọi đã bắt đầu trên target cũ và không thay thế locking/coordination cho mọi state khác của ứng dụng.

### 3.3. `VolatileCallSite`: khả năng nhìn thấy thay đổi mạnh hơn

~~~java
VolatileCallSite site = new VolatileCallSite(upperHandle);
site.setTarget(lowerHandle);
~~~

Target của volatile site tuân theo ngữ nghĩa đọc/ghi tương tự **volatile variable**. Không có `VolatileCallSite.syncAll` vì cập nhật target đã mang visibility phù hợp. Với dynamic invoker liên kết tới site này, các lời gọi mới phải quan sát target theo quy tắc volatile; vẫn không có lời hứa rằng một tác vụ đã bắt đầu trước khi thay target sẽ bị chuyển hướng giữa chừng.

Đừng kết luận volatile site “luôn nhanh hơn”, “luôn an toàn cho mọi state chia sẻ”, hay “thay thế synchronized” trong mọi workflow. Nó xử lý **visibility/order của biến target**, không giải quyết nguyên tử của một transaction nghiệp vụ gồm nhiều biến.

## 4. `getTarget()` khác `dynamicInvoker()` ở điểm quyết định

Một nhầm lẫn phổ biến: “Nếu tôi đã lấy handle từ CallSite, handle đó tự thay theo site”.

Không phải lúc nào cũng thế.

~~~java
MethodHandle saved = site.getTarget();
MethodHandle viaSite = site.dynamicInvoker();

site.setTarget(anotherTarget);
~~~

Đoạn minh họa giả định `site` thuộc loại mutable/volatile và các handle đều cùng type.

- `saved` là **MethodHandle được đọc ở thời điểm đó**. Việc thay target của site **không biến đổi** object handle đã lưu; gọi `saved` về sau vẫn thực hiện đường gọi mà `saved` biểu diễn.
- `viaSite` là **MethodHandle luôn tra qua trạng thái target hiện hành của site**, theo quy tắc memory visibility của subclass. Sau relink, cùng object `viaSite` có thể chuyển sang target mới.
- `site.getTarget()` sau relink sẽ trả handle mới (theo cùng quy tắc visibility), nhưng mỗi lần đọc là một thao tác khác với việc duy trì dynamic invoker.

Đây là lý do một hệ thống có thể **cấp cho caller một invoker ổn định** trong khi bên trong thay implementation mà caller không phải tạo lại handle.

### 4.1. Đừng nhầm bản thân `MethodHandle` với “con trỏ phương thức mutable”

`MethodHandle` là một tham chiếu gọi đã có type. Bạn có thể xây handle khác bằng `asType`, `bindTo`, `filterArguments`..., nhưng **không gọi `setTarget` trên chính MethodHandle**. Việc trỏ qua target có thể thay đổi thuộc trách nhiệm của **CallSite**.

### 4.2. Dynamic invoker có Type gì?

`site.dynamicInvoker().type()` bằng `site.type()`. Nếu site là `(String)String` thì caller của dynamic invoker phải thực hiện lời gọi có kiểu phù hợp. Khi dùng `invokeExact`, **kiểu tĩnh của đối số và kiểu kết quả** tại nơi gọi phải chính xác. Nếu dùng `invoke`, JVM có thể tạo adapter khi `asType` hỗ trợ, nhưng sự thích nghi này **không làm thay `CallSite.type()`**.

## 5. Thực hành Java 17+: cố định kiểu, thay target, kiểm tra lỗi

Bài thực hành là một chương trình **độc lập**, có đủ imports và method. Nó tạo ba loại CallSite và giải thích đúng sự khác nhau giữa:

- Tạo site gắn chặt vào target.
- Tạo site có type nhưng chưa có target thực thi nghiệp vụ.
- Gọi thông qua dynamic invoker rồi thay target hai lần.
- Lấy một snapshot của handle cũ bằng `getTarget()`.
- Thử gán handle sai kiểu và thích nghi bằng `asType` trước khi gán.
- Thử volatile site.

**Tệp:** `CallSiteTargetDemo.java`

~~~java
import java.lang.invoke.*;
import java.util.Locale;

public final class CallSiteTargetDemo {
    public static String upper(String value) {
        return value.toUpperCase(Locale.ROOT);
    }

    public static String lower(String value) {
        return value.toLowerCase(Locale.ROOT);
    }

    public static Object wrap(Object value) {
        return "<" + value + ">";
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType contract = MethodType.methodType(String.class, String.class);
        MethodHandle upperHandle = lookup.findStatic(
                CallSiteTargetDemo.class, "upper", contract);
        MethodHandle lowerHandle = lookup.findStatic(
                CallSiteTargetDemo.class, "lower", contract);
        MethodHandle objectHandle = lookup.findStatic(
                CallSiteTargetDemo.class, "wrap",
                MethodType.methodType(Object.class, Object.class));

        ConstantCallSite constant = new ConstantCallSite(upperHandle);
        System.out.println("constantType=" + constant.type());
        System.out.println("constant=" +
                (String) constant.dynamicInvoker().invokeExact("Java"));
        try {
            constant.setTarget(lowerHandle);
        } catch (UnsupportedOperationException expected) {
            System.out.println("constantChange=blocked");
        }

        MutableCallSite mutable = new MutableCallSite(contract);
        MethodHandle invoker = mutable.dynamicInvoker();
        System.out.println("mutableType=" + mutable.type());
        try {
            String ignored = (String) invoker.invokeExact("Java");
            System.out.println("unexpected=" + ignored);
        } catch (IllegalStateException expected) {
            System.out.println("uninitialized=IllegalStateException");
        }

        mutable.setTarget(upperHandle);
        MethodHandle snapshot = mutable.getTarget();
        System.out.println("first=" + (String) invoker.invokeExact("Java"));

        mutable.setTarget(lowerHandle);
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("second=" + (String) invoker.invokeExact("Java"));
        System.out.println("snapshot=" + (String) snapshot.invokeExact("Java"));
        System.out.println("sameType=" +
                mutable.type().equals(mutable.getTarget().type()));

        try {
            mutable.setTarget(objectHandle);
        } catch (WrongMethodTypeException expected) {
            System.out.println("wrongTarget=WrongMethodTypeException");
        }
        System.out.println("afterRejected=" +
                (String) invoker.invokeExact("Java"));

        mutable.setTarget(objectHandle.asType(contract));
        MutableCallSite.syncAll(new MutableCallSite[]{mutable});
        System.out.println("adaptedTarget=" +
                (String) invoker.invokeExact("Java"));

        VolatileCallSite volatileSite = new VolatileCallSite(upperHandle);
        MethodHandle volatileInvoker = volatileSite.dynamicInvoker();
        volatileSite.setTarget(lowerHandle);
        System.out.println("volatile=" +
                (String) volatileInvoker.invokeExact("JaVa"));
        System.out.println("volatileType=" + volatileSite.type());
    }
}
~~~

### 5.1. Biên dịch và chạy

Lưu đúng tên file, dùng JDK 17 trở lên. Từ thư mục chứa file:

~~~bash
javac --release 17 -d out CallSiteTargetDemo.java
java -cp out CallSiteTargetDemo
~~~

`javac -d out` có thể tạo output directory nếu chưa có. Java 17 là target của ví dụ; chương trình dùng `Locale.ROOT` để chuyển chữ hoa/thường có kết quả độc lập locale người dùng.

### 5.2. Stdout chính xác đã kiểm chứng

~~~text
constantType=(String)String
constant=JAVA
constantChange=blocked
mutableType=(String)String
uninitialized=IllegalStateException
first=JAVA
second=java
snapshot=JAVA
sameType=true
wrongTarget=WrongMethodTypeException
afterRejected=java
adaptedTarget=<Java>
volatile=java
volatileType=(String)String
~~~

Mã nguồn trên đã được **biên dịch bằng `javac --release 17` và chạy `java` thành công**.

### 5.3. Giải thích chi tiết kết quả

**`constantType=(String)String`**: `ConstantCallSite` lấy type từ `upperHandle`. `constant=JAVA` minh họa dynamic invoker của constant site thực thi target bất biến. `constantChange=blocked` xác nhận `ConstantCallSite.setTarget` luôn bị từ chối.

**`mutableType=(String)String`** xuất hiện **ngay cả khi site chưa có target nghiệp vụ**. Constructor `MutableCallSite(MethodType)` đã tạo target mặc định cùng kiểu nhưng ném lỗi. Do đó `uninitialized=IllegalStateException` không phải type mismatch và không phải `NullPointerException`.

**`first=JAVA` rồi `second=java`**: trước/sau khi `setTarget` lần lượt dùng `upperHandle`/`lowerHandle`. `invoker` được tạo **một lần** nhưng liên tục chuyển qua site. Lệnh `syncAll` trong demo đơn luồng được gọi để thể hiện đúng API; mục đích thiết yếu của nó là **phối hợp visibility giữa thread**, không phải điều kiện bắt buộc để cùng thread thấy update.

**`snapshot=JAVA`**: `snapshot` giữ handle của target trước khi đổi; nó **không đi qua site** nên tiếp tục gọi uppercase. `sameType=true` cho thấy `site.type()` và `getTarget().type()` vẫn bằng nhau dù target đã thay.

**`wrongTarget=WrongMethodTypeException`**: `objectHandle` có type `(Object)Object`, không bằng `(String)String`. Thử gán thất bại **trước khi thay target**, nên `afterRejected=java` vẫn gọi `lower`.

**`adaptedTarget=<Java>`**: `objectHandle.asType(contract)` tạo một **handle adapter mới** có type `(String)String`; wrapper sẽ chuyển arguments/results hợp lệ giữa `String` và `Object`. Adapter gọi `wrap` rồi chuyển kết quả `Object` chứa String về `String`. Nội dung `<Java>` là logic của `wrap`, không liên quan đến lỗi type trước đó.

**`volatile=java`, `volatileType=(String)String`**: volatile site có thể đổi từ upper sang lower nhưng type không đổi. Ví dụ này là đơn luồng; **khả năng quan sát cập nhật giữa nhiều thread** được quy định bởi Java memory semantics và tài liệu API, không được suy ra chỉ từ stdout của demo.

## 6. `MethodHandle.asType`: thích nghi target nhưng giữ CallSite contract

Khi thư viện có một target `(Object)Object` nhưng muốn expose call site `(String)String`, cần tạo adapter:

~~~java
MethodType contract = MethodType.methodType(String.class, String.class);
MethodHandle adapted = objectHandle.asType(contract);
site.setTarget(adapted);
~~~

Đây là **đoạn minh họa** với `objectHandle` và `site` có sẵn, không phải file chạy độc lập.

Điểm cần hiểu:

- `objectHandle.type()` vẫn là `(Object)Object`. `adapted.type()` mới là `(String)String`.
- `asType` chỉ thành công khi JVM hỗ trợ các chuyển đổi kiểu tương ứng (reference cast, một số boxing/unboxing/primitive conversion...). Không phải mọi chuyển đổi đều hợp lệ.
- `site.setTarget(adapted)` kiểm tra **MethodType của adapter**. Nó không cần biết method gốc phía trong dùng `Object` hay `String`, miễn kết nối qua adapter hợp lệ.
- Nếu một phép ép kiểu **giá trị runtime** của adapter không thành công, caller vẫn có thể gặp `ClassCastException`, ngay cả khi site.type() hoàn toàn hợp lệ.
- Thay `MethodType` công khai của site thường có nghĩa phải tạo **site mới** với contract mới và thay đường liên kết ở cấp cao hơn; không thể `setTarget` một handle với type khác chỉ để nâng phiên bản API.

### 6.1. Không nhầm với `invoke` và `invokeExact`

`MethodHandle.invokeExact` là lời gọi yêu cầu descriptor tại nơi gọi **trùng hoàn toàn** kiểu handle nhận; `invoke` cho phép một mức thích nghi như `asType` khi hợp lệ. Đây là kiểm tra **trên lời gọi handle**.

Còn `CallSite.setTarget` là kiểm tra **trên việc thay target của site**. Hai tầng khác nhau:

~~~text
Caller -> (invokeExact) -> dynamicInvoker:(String)String
                              |
                              v
                          CallSite
                          type=(String)String
                              |
                          setTarget chỉ nhận
                          MethodHandle:(String)String
                              |
                              v
                         target logic
~~~

Nếu caller đổi kiểu tĩnh của đối số hoặc kiểu kết quả của `invokeExact`, có thể bị `WrongMethodTypeException` dù site.target hoàn toàn hợp lệ. Ngược lại, nếu `setTarget` thất bại, caller vẫn có thể gọi target cũ bình thường.

## 7. `CallSite` liên hệ thế nào với `invokedynamic`?

### 7.1. Bootstrap method trả về CallSite

Trong class file có `invokedynamic`, mỗi symbolic dynamic call site có **tên**, **method descriptor**, và chỉ dẫn đến **bootstrap method** (cùng các static arguments có thể có). Khi liên kết điểm gọi đó, JVM gọi bootstrap để nhận một `CallSite`. Chữ ký bootstrap thường có ba tham số đầu:

~~~text
MethodHandles.Lookup caller
String invokedName
MethodType invokedType
~~~

Sau đó có thể có static bootstrap arguments theo cơ chế JVM. `MethodType invokedType` mô tả **hợp đồng của instruction `invokedynamic` đang liên kết**, ví dụ `(String)String`.

Kết quả bootstrap phải là **CallSite hợp lệ và có type tương thích chính xác với descriptor**. JVM liên kết site được chấp nhận với instruction; khi instruction chạy, nó gọi target hiện tại của site như một lời gọi chính xác theo kiểu đã xác nhận.

~~~text
Class-file invokedynamic
 name="transform"
 descriptor=(String)String
 bootstrap=linker(...)
          |
          v
 JVM gọi bootstrap(Lookup, "transform", MethodType(String)String, ...)
          |
          v
 CallSite.type() phải bằng MethodType được yêu cầu
          |
          v
 JVM liên kết instruction với CallSite
          |
          +-> ConstantCallSite: luôn target ban đầu
          |
          +-> Mutable/VolatileCallSite: target có thể relink
                  (nhưng type luôn giữ nguyên)
~~~

**Bất biến được dùng ở tầng JVM:** nếu một `invokedynamic` đã liên kết thành công, target của CallSite luôn có type đúng với call-site descriptor đã liên kết. Vì vậy **bản thân instruction `invokedynamic` đã liên kết hợp lệ sẽ không tự ném `WrongMethodTypeException` do mismatch descriptor/target**. Exception của logic target, adapter khác, hoặc quá trình bootstrap vẫn có thể xảy ra.

### 7.2. Mismatch lúc bootstrap không phải chuyện có thể bỏ qua

Giả sử JVM yêu cầu:

~~~text
invokedType=(String)String
~~~

nhưng bootstrap trả:

~~~text
site.type()=(Object)Object
~~~

Dù String là Object, đó không phải chữ ký bằng nhau. **Liên kết `invokedynamic` không hợp lệ** và có thể kết thúc bằng `BootstrapMethodError` theo quy tắc resolution của JVM, thay vì site “tự đoán” cách chuyển đổi. Trách nhiệm của bootstrap là trả site đúng type, ví dụ chọn target đã được `asType(invokedType)` khi chuyển đổi hợp lệ, rồi tạo `ConstantCallSite` hoặc mutable/volatile site phù hợp.

Đoạn minh họa một bootstrap **ở bên trong class có method static phù hợp**:

~~~java
public static CallSite bootstrap(MethodHandles.Lookup caller,
                                 String name,
                                 MethodType type) throws Throwable {
    MethodHandle target = caller.findStatic(
            caller.lookupClass(), "transformImpl",
            MethodType.methodType(String.class, String.class));
    return new ConstantCallSite(target.asType(type));
}
~~~

Đây là **snippet minh họa**, **không phải chương trình chạy độc lập**: giả định class mà `caller.lookupClass()` đại diện có static method `transformImpl(String)String` và quyền truy cập phù hợp. Nó minh họa việc bootstrap dùng `type` do JVM cung cấp; không có lời hứa rằng `asType` hỗ trợ mọi kiểu yêu cầu.

### 7.3. Tự tạo site trong Java không phát sinh `invokedynamic`

Trong demo mục 5, chúng ta viết:

~~~java
MutableCallSite site = new MutableCallSite(contract);
MethodHandle invoker = site.dynamicInvoker();
String text = (String) invoker.invokeExact("Java");
~~~

**Chỉ là Java code tự tạo một CallSite “free-floating”**. Không có `invokedynamic` được tạo thêm chỉ bởi lệnh `new MutableCallSite(...)` hay `dynamicInvoker()`.

Cụ thể:

- `invoker.invokeExact(...)` là một lời gọi **`MethodHandle.invokeExact`** (signature polymorphic), bình thường biên dịch thành **`invokevirtual`**.
- `invokedynamic` là **instruction bytecode riêng**, được phát sinh bởi một số công cụ/compiler và gắn với bootstrap method từ constant pool.
- Một `CallSite` có thể liên kết với **không có instruction nào** (“free-floating”) hoặc được dùng để phục vụ một/hay nhiều điểm gọi theo thiết kế JVM. Không nên đồng nhất bản thân object CallSite với một dòng mã nguồn duy nhất.
- Java lambda hay string concatenation có thể dùng `invokedynamic` trên một số classfile do `javac` sinh; nhưng câu chuyện sử dụng cụ thể phụ thuộc compiler, runtime, và transformation. Để **kiểm chứng instruction thật**, cần xem bytecode bằng `javap -v -c` trên classfile tương ứng.

### 7.4. Mối liên hệ với động từ “relink”

Sau bootstrap liên kết một `invokedynamic`, **không cần gọi bootstrap mỗi lần chạy**. Nếu dùng Mutable/VolatileCallSite, phần điều phối có thể **đổi target của chính site**; instruction đã liên kết vẫn giữ kiểu gọi cũ nhưng hướng thực thi tới target mới.

Vì thế “relink dynamic dispatch” trong nhiều thư viện runtime thường là **cập nhật target của một call site đã tồn tại**, chứ không phải sửa lại source hoặc bytecode descriptor tại nơi gọi.

Lưu ý về concurrency của bootstrap: JVM có thể có nhiều thread tham gia resolution và việc thực thi bootstrap có thể diễn ra đồng thời trong một số tình huống; JVM chọn và cài đặt kết quả phù hợp. Đừng khẳng định bootstrap Java code của bạn chắc chắn chỉ chạy đúng một lần trong mọi race — hãy thiết kế bootstrap/registry an toàn với concurrency.

## 8. Đồng bộ nhiều thread: chọn `MutableCallSite` hay `VolatileCallSite`?

Chỉ thay target trên một thread và gọi ngay trên cùng thread **không đủ** để đánh giá visibility khi hệ thống có nhiều worker threads.

### 8.1. Mutable site là trường bình thường

`MutableCallSite.setTarget` có ngữ nghĩa write của một trường thường. Các thread khác có thể chưa thấy cập nhật vì cache hoặc tối ưu hợp lệ theo Java Memory Model; Java không hứa rằng mọi lần gọi trên thread khác sẽ nhìn thấy target mới ngay lập tức chỉ nhờ `setTarget`.

Khi cần công bố cập nhật tới caller, có thể dùng:

~~~java
site.setTarget(nextTarget);
MutableCallSite.syncAll(new MutableCallSite[]{site});
~~~

Đây là **snippet minh họa**, cần biến đúng type. `syncAll` thực hiện hành động đồng bộ để các thread phải loại bỏ giá trị target cũ đã cache và chấp nhận trạng thái đã được công bố; cần phối hợp `setTarget`/`syncAll` để tránh race giữa các writer.

Tại một thời điểm chuyển tiếp, một số call đã **bắt đầu** có thể đang chạy target cũ; `syncAll` không rollback chúng. Ngoài ra `syncAll` có thể tốn kém; nếu thay nhiều site, cân nhắc gom batch và không sử dụng nó như một vòng lặp “polling liên tục” vô nghĩa.

### 8.2. Volatile site có visibility ngay trên biến target

`VolatileCallSite` định nghĩa target giống volatile field, có độ bảo đảm visibility mạnh hơn giữa thread mà không cần `syncAll`. Điều này thích hợp cho trạng thái target thường xuyên cập nhật hoặc cần guarantee rõ ở mỗi lần đọc.

Nhưng:

- Đổi target **không** bảo đảm một giao dịch gồm nhiều cấu hình khác nhau cập nhật nguyên tử.
- Lời gọi đã bắt đầu trước một lần thay target vẫn có thể chạy target cũ.
- Volatile semantics không thay thế thread-safe design bên trong **target method**.
- Không chọn theo cảm giác hiệu năng; đo đạc nếu hệ thống có yêu cầu latency/throughput.

### 8.3. So sánh nhanh

| Tình huống | Lựa chọn |
| --- | --- |
| Liên kết bất biến suốt vòng đời ứng dụng | `ConstantCallSite` |
| Cập nhật ít, theo đợt, có thể điều phối `syncAll` | `MutableCallSite` |
| Cập nhật cần visibility kiểu volatile giữa thread | `VolatileCallSite` |
| Muốn thay danh sách tham số hoặc return type | **Không thể trên cùng CallSite**; thiết kế call site khác/adapter versioning |
| Chỉ cần gọi một MethodHandle đã biết, không cần liên kết động | Có thể dùng trực tiếp `MethodHandle`; không nhất thiết thêm CallSite |

## 9. Thiết kế ứng dụng: ổn định interface, linh hoạt implementation

### 9.1. Plugin router

Một plugin router cung cấp API public `String transform(String input)`. Nó có thể liên kết site `(String)String` đến plugin A, rồi đổi sang plugin B:

~~~text
Plugin A: transform(String)String
Plugin B: transform(String)String
                  |
                  v
      CallSite:(String)String
                  |
          dynamicInvoker()
                  |
                Caller
~~~

Khi chọn target, yêu cầu **cùng chữ ký**. Nếu plugin thực tế nhận `Object` hoặc trả type khác, router phải tạo adapter thích hợp **trước khi `setTarget`** và kiểm tra cả semantics của conversion. Không nên che một thay đổi không tương thích chỉ bằng cast mù quáng.

Một hệ thống production còn cần:

- Xác định lifecycle plugin, quyền truy cập `Lookup` và class loaders. `CallSite` không tự giải quyết `IllegalAccessException` khi tạo MethodHandle.
- Quy tắc fallback khi plugin ném lỗi hoặc không tìm thấy method.
- Chính sách cho in-flight calls nếu chuyển plugin giữa chừng.
- Kế hoạch dọn tài nguyên, kiểm soát memory leak do giữ class loaders hoặc handle cũ trong cache.
- Kiểm tra tương thích **hành vi**, không chỉ cùng `MethodType`.

### 9.2. Inline cache và dynamic language runtime

Trong dynamic runtime, một inline cache có thể bắt đầu với generic dispatch handle, sau đó đổi target thành nhánh đã được tối ưu cho kiểu đối số thường gặp:

~~~text
invoke site type=(Object)Object
    |
    +-- target: genericDispatch
    |
    +-- after observation:
          target: guardedFastPath (still (Object)Object)
~~~

Một nhánh `guardWithTest`/`asType`/`dropArguments` có thể giúp giữ **kiểu ngoài của site** trong khi thay cách thực thi phía trong. **Điều kiện bắt buộc** vẫn là handle cuối cùng được cài vào site phải có **`.type()` chính xác bằng `site.type()`**.

Nếu branch bên trong dựa trên một kiểu chuyên biệt (ví dụ `String`), hãy dùng adapter để chuyển đổi theo contract và có fallback hợp lý, thay vì thay type của site theo dữ liệu đầu vào từng lần.

### 9.3. Public contract không thể thay chỉ vì implementation đổi

Mô hình có hai chiều tiến hóa:

- **Tiến hóa target**: thay logic, cache, tối ưu hoặc provider nhưng giữ cùng `MethodType`.
- **Tiến hóa API**: đổi số lượng/thứ tự/kiểu tham số hoặc return type. Việc này tạo hợp đồng khác, phải được version/migrate; `setTarget` không phải cơ chế tự động sửa call sites cũ.

Vì thế CallSite giúp tách **cơ chế dispatch** khỏi **cấu trúc chữ ký**, không xóa bỏ nhu cầu thiết kế API ổn định.

## 10. Những lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `WrongMethodTypeException` ngay ở `setTarget` | Target mới có `MethodType` không bằng site type | In `site.type()` và `newTarget.type()`; so `equals` |
| `ConstantCallSite.setTarget` ném `UnsupportedOperationException` | Constant site không đổi target được | Chọn mutable/volatile site ngay từ thiết kế |
| `IllegalStateException` khi gọi mutable site mới tạo bằng `MethodType` | Target mặc định là handle cùng type nhưng luôn ném lỗi | Gán target thực tế trước khi cho caller dùng |
| `WrongMethodTypeException` lúc `invokeExact` dù target đã hợp lệ | Descriptor ở **nơi gọi invoker** sai kiểu tham số/return | Kiểm tra cast trực tiếp, kiểu tĩnh và `invoker.type()` |
| Sau thay target, một biến `savedHandle` vẫn gọi logic cũ | Biến lấy từ `getTarget()` là snapshot | Dùng `dynamicInvoker()` nếu muốn theo site |
| Thread khác nhìn target cũ lâu | Dùng `MutableCallSite` thiếu visibility/sync | Điều phối `syncAll` hoặc cân nhắc `VolatileCallSite` |
| `ClassCastException` sau khi dùng `asType` | Conversion về mặt method type hợp lệ nhưng giá trị runtime sai kiểu | Xác minh loại giá trị thật, boundary adapter |
| `IllegalAccessException` khi tạo MethodHandle | `Lookup` thiếu quyền truy cập class/member/JPMS | Kiểm tra module/package/modifiers, không sửa CallSite.type để né quyền |
| Lỗi bootstrap của `invokedynamic` | Bootstrap ném lỗi, trả sai loại hoặc site type không bằng descriptor được yêu cầu | Kiểm tra `BootstrapMethodError`, `invokedType` và `site.type()` |
| `NullPointerException` khi `setTarget` | Truyền null thay vì một `MethodHandle` hợp lệ | Validate target trước khi cài |
| Kết quả có vẻ “đổi kiểu” sau relink | Nhầm type của value bên trong `Object` với `MethodType` ở boundary | In `site.type()`, `getTarget().type()`, kiểm tra cast |
| Ứng dụng giữ plugin cũ không giải phóng được | Cache invoker/handle giữ reference tới class hoặc loader | Kiểm tra class loader lifecycle và ownership |

**Quy trình debug tối thiểu:**

1. In `site.getClass().getName()` để biết constant, mutable hay volatile.
2. In `site.type()`, `site.getTarget().type()` và `site.dynamicInvoker().type()`; chúng phải biểu diễn cùng contract.
3. Khi relink, in `newTarget.type()` **trước `setTarget`**; kiểm tra khả năng `asType` nếu cần.
4. Xác nhận caller muốn **snapshot** hay **dynamic invoker**.
5. Nếu có nhiều thread, kiểm tra visibility, `syncAll`, ordering của writer và các state khác.
6. Nếu gắn với `invokedynamic` thật, kiểm tra bootstrap method và descriptor constant pool; tách **linkage error** khỏi exception của logic target.
7. Nếu lỗi từ target, log nguyên nhân target và lifecycle resource; không đổ mọi lỗi cho `MethodType`.

**Lưu ý công cụ:** `javap -v -c` cho thấy các `invokedynamic` instruction có thật và BootstrapMethods attribute (nếu classfile chứa chúng). Mã demo **tự tạo CallSite** không chủ ý phát sinh `invokedynamic` cho riêng lời gọi `invoker.invokeExact`. Đừng nhầm giữa việc quan sát `invokevirtual MethodHandle.invokeExact` trong demo và một `invokedynamic` được JVM liên kết bằng bootstrap.

## 11. Bài tập tự kiểm tra

**Bài 1 — Phân biệt type và target.** Với site `(String)String`, hãy giải thích vì sao chuyển từ `upper(String)` sang `lower(String)` hợp lệ, nhưng chuyển trực tiếp sang `wrap(Object)Object` thất bại dù cả hai cùng có thể xử lý String.

**Bài 2 — Snapshot hay live routing?** Chạy lại demo, đổi vị trí tạo `snapshot` thành **sau** `setTarget(lowerHandle)`. Dự đoán `snapshot` và `second` thay đổi thế nào. Vì sao dynamic invoker vẫn không cần tạo lại?

**Bài 3 — Sai kiểu trả về.** Tạo handle cho `int length(String)` và thử `mutable.setTarget(...)` ở site `(String)String`. Dự đoán exception và giải thích vì sao chỉ khác return type vẫn không hợp lệ.

**Bài 4 — Uninitialized site.** Tạo `new MutableCallSite(MethodType.methodType(int.class))`, gọi `dynamicInvoker` trước `setTarget` và giải thích tại sao lỗi không phải `WrongMethodTypeException` nếu caller gọi với descriptor phù hợp.

**Bài 5 — Adaptation.** Cho target `(Object)Object` trả về một `Integer`. Dùng `asType((String)String)` và gọi với String. Xác định loại lỗi có thể xuất hiện lúc thực thi, dù `site.setTarget` đã thành công.

**Bài 6 — Thread visibility.** Thiết kế hai phiên bản router: (A) `MutableCallSite` cộng `syncAll` theo batch, (B) `VolatileCallSite`. Nêu trade-off về tính mới của liên kết, chi phí và khả năng một lời gọi đang chạy tiếp tục target cũ.

**Bài 7 — `invokedynamic` thực tế.** Kiểm tra một classfile có `invokedynamic` bằng `javap -v -c`. Xác định bootstrap reference và descriptor của instruction. Giải thích vì sao `CallSite.type()` phải khớp descriptor ấy, nhưng target mutable có thể thay về sau.

**Bài 8 — Tách contract khỏi business semantics.** Hai target cùng `(String)String` nhưng một target gửi dữ liệu ra mạng, một target chỉ chuyển chữ hoa. Tại sao `CallSite.type()` bằng nhau không thể thay thế kiểm tra quyền truy cập, audit và tính tương thích nghiệp vụ?

## 12. Kết luận

**`CallSite` giữ một `MethodHandle` là `target`, nhưng `CallSite.type()` là bất biến trong suốt vòng đời site.** Với Mutable/VolatileCallSite, `setTarget` đổi được đích thực thi **chỉ khi new target có cùng `MethodType`**; sai kiểu bị từ chối, còn ConstantCallSite không cho đổi target. `dynamicInvoker()` đem lại đường gọi ổn định nhưng luôn đi qua target của site, khác với việc lưu snapshot từ `getTarget()`. Khi `CallSite` được liên kết với `invokedynamic`, bất biến kiểu này giúp descriptor của instruction đã liên kết tiếp tục đúng dù implementation bên dưới được relink.

Hãy nhớ mô hình một dòng:

~~~text
CallSite = (MethodType cố định) + (target MethodHandle theo chính sách constant/mutable/volatile)
~~~

## Tài liệu tham khảo chính thức (Java 17)

- [Java SE 17 — `CallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [Java SE 17 — `ConstantCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html)
- [Java SE 17 — `MutableCallSite` và `syncAll`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html)
- [Java SE 17 — `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html)
- [Java SE 17 — `MethodHandle.asType` và `invokeExact`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html)
- [JVM Specification 17 — `5.4.3.6` Dynamic call site resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVM Specification 17 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.invokedynamic)
