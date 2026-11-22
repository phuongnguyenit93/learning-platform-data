# Khử lời gọi ảo dựa trên thông tin kiểu và giới hạn của giả định

**Devirtualization (khử lời gọi ảo)** là một nhóm tối ưu hóa của JIT compiler nhằm biến một lời gọi có khả năng **dispatch động** đến nhiều implementation thành **đường gọi trực tiếp** tới đích phù hợp, hoặc thành **các nhánh có kiểm tra kiểu** mà nhánh phổ biến có thể chạy trực tiếp. Khi đã biết đích, JIT có thêm cơ hội **method inlining**, constant propagation, dead-code elimination, escape analysis và những tối ưu khác.

Trong **HotSpot JVM**, thông tin được dùng có thể đến từ:

1. **Kiến thức tĩnh chắc chắn**, chẳng hạn receiver có exact runtime type đã được chứng minh hoặc method không thể bị override.
2. **Class Hierarchy Analysis (CHA)**: phân tích các class/hierarchy **đang được JVM biết tới** để tìm một method target duy nhất; nếu chương trình có thể nạp class mới, compiled code phải có cơ chế theo dõi/thu hồi giả định.
3. **Type profiling**: dữ liệu HotSpot thu thập tại **call site** về concrete receiver classes thực tế, ví dụ một site gần như chỉ thấy một type.
4. **Các ràng buộc từ flow analysis**: type checks, casts, allocations và kiểm tra nhánh có thể thu hẹp tập receiver types trên một execution path.

**Không được hiểu** devirtualization là thay đổi semantics của Java. Java vẫn phải gọi đúng implementation theo **runtime class của receiver**, tuân thủ khả năng nạp class động, overload/override, null checks, exceptions và Java Memory Model. Tối ưu hóa phỏng đoán có thể bị hủy qua **deoptimization** hoặc đi sang một **fallback dispatch path** khi giả định sai.

Bài tập trung vào các tối ưu này trong **HotSpot với JDK 17+**. CHA, type-profile-based speculation, inline caches, compiled nmethods và C1/C2 là **implementation details**, không phải một cam kết rằng mọi JVM sử dụng cùng thuật toán hoặc luôn khử được mọi lời gọi ảo.

## 1. Dispatch động là gì?

Xét một interface:

```java
interface Payment {
    int calculate(int amount);
}

final class StandardPayment implements Payment {
    @Override
    public int calculate(int amount) {
        return amount + 2;
    }
}

final class PremiumPayment implements Payment {
    @Override
    public int calculate(int amount) {
        return amount * 2;
    }
}
```

Đây là các class/interface hợp lệ, nhưng đoạn này **chưa có `main`**. Một method sử dụng interface:

```java
static int pay(Payment payment, int amount) {
    return payment.calculate(amount);
}
```

Nếu đặt method vào một class hợp lệ, kiểu tĩnh của `payment` là `Payment`. Nhưng trong runtime, `payment` có thể trỏ đến `StandardPayment` hoặc `PremiumPayment`; hai implementation trả về các giá trị khác nhau.

```text
Call site: payment.calculate(amount)
                    │
                    ▼
          runtime receiver class?
                /       \
               /         \
    StandardPayment   PremiumPayment
       amount + 2       amount * 2
```

**Java-level semantics:** đích phụ thuộc receiver runtime type. Không được suy từ **khai báo biến kiểu `Payment`** rằng JVM chắc chắn gọi một class cụ thể.

### Đặc tính của polymorphism

- **Overloading**: chọn chữ ký method theo luật compile-time của Java; là vấn đề khác.
- **Overriding**: subclass/interface implementation định nghĩa method tương ứng; runtime dispatch chọn implementation phù hợp.
- **Dynamic dispatch**: điều khiển lựa chọn method theo runtime type khi lệnh gọi có dynamic-dispatch semantics.
- **Devirtualization**: tối ưu cách thực thi dispatch; **không xóa quyền override** mà Java cho phép.

**Điểm mấu chốt:** cùng một call site bytecode có thể gọi những concrete methods khác nhau ở những thời điểm khác nhau nếu receiver types khác nhau.

## 2. Bytecode liên quan: invokevirtual và invokeinterface

JVM có các instruction gọi method khác nhau:

| JVM opcode | Vai trò chính | Liên quan tới devirtualization |
| --- | --- | --- |
| `invokevirtual` | Lời gọi instance method có dispatch theo runtime class | Có thể được HotSpot khử dispatch khi đích xác định |
| `invokeinterface` | Lời gọi method thông qua interface; tìm implementation phù hợp | Có thể được optimize bằng CHA/type profile |
| `invokespecial` | Gọi constructor, `super` và một số instance method theo luật đặc biệt | Không tương đương generic virtual dispatch |
| `invokestatic` | Gọi static method | Không phải lời gọi receiver động |
| `invokedynamic` | Dynamic call site được link qua bootstrap method | Cơ chế liên kết riêng; không đánh đồng với `invokevirtual` |

Ví dụ trên, `payment.calculate(amount)` thường được `javac` chuyển thành **`invokeinterface`** vì chữ ký call site dùng interface. Nếu dùng kiểu tĩnh là một non-interface class, lời gọi instance method có thể thể hiện bằng **`invokevirtual`**.

**Quan trọng về từ ngữ:** một bytecode `invokevirtual` **không chứng minh** CPU phải làm vtable lookup ở mọi lần chạy. JIT có thể biến nó thành direct call hoặc inline; `javap -c` vẫn in bytecode cũ vì JIT không phải sửa class file.

### Direct binding khác JIT devirtualization

Nếu method là `static`, JVM đã dùng `invokestatic`; đấy **không phải** bài toán loại bỏ dynamic dispatch của một call site vốn có thể đa hình. Tương tự, `super.method()` và constructor dùng `invokespecial` theo luật riêng.

Một method `final` hoặc class `final` có thể khiến compiler xác định target tĩnh ngay cả khi bytecode vẫn là `invokevirtual`. Cái cần xét là **khả năng override/đích thực tế**, không chỉ tên opcode.

## 3. Đường thực thi trước và sau tối ưu

**Trước tối ưu (mô hình logic):**

```text
load receiver
  │
  ├─ null? → NullPointerException theo semantics
  │
  ▼
resolve/dispatch đến concrete target
  │
  ▼
call implementation đúng
```

**Sau khi JIT có căn cứ cho một target phổ biến:**

```text
load receiver
  │
  ├─ null semantics vẫn phải đúng
  │
  ▼
check receiver type == HotClass?
       │              │
      yes             no
       │              │
       ▼              ▼
inlined/direct     generic virtual dispatch
HotClass path      hoặc uncommon trap
       │              │
       └──────────────┘
                 │
                 ▼
            đúng kết quả Java
```

Đây là sơ đồ conceptual. Trong machine code thực tế, null check có thể dùng **implicit null check**, guard có thể được hoán đổi/hợp nhất, và nhánh miss có thể dùng **deoptimization**, **runtime stub** hoặc fallback virtual call. Không có cam kết tất cả HotSpot versions chèn đúng một phép `instanceof` hoặc check `getClass()` theo thứ tự như hình.

### Khử lời gọi ảo không nhất thiết là inlining

- **Devirtualization**: xác định hoặc thu hẹp **callee target** để tránh dispatch tổng quát ở hot path.
- **Inlining**: đặt logic method được gọi **vào code của caller**, loại bỏ nhu cầu một call boundary riêng ở path đó.
- Có thể **devirtualize nhưng không inline**, nếu callee quá lớn, compiler budget hết, hoặc heuristic không thấy lợi.
- Có thể **inline nhiều target** trong các nhánh guarded polymorphic call site.
- Inlining mở đường cho nhiều tối ưu xuyên method, nhưng làm code size tăng, có thể gây áp lực lên **code cache** và instruction cache.

Đừng xem log “`inline (hot)`” là một chứng nhận rằng **mọi** lời gọi qua interface trong ứng dụng đã chuyển thành direct/inlined code.

## 4. Trường hợp có thể xác định đích chắc chắn

Có những thông tin giúp JIT **chứng minh** một method call không có nhiều target hợp lệ trên đường thực thi liên quan.

### 4.1. Class `final`

```java
final class FixedCalculator {
    int compute(int x) {
        return x + 1;
    }
}
```

`FixedCalculator` không thể có subclass hợp lệ theo luật Java. Nếu receiver có exact runtime class này và method cụ thể không có dispatch biến thể khác, việc xác định đích rất thuận lợi. Nhưng **tối ưu vẫn phụ thuộc compiler policy**: không có hợp đồng rằng method luôn được inline hay code chỉ gồm một phép cộng.

### 4.2. Method `final`

```java
class Base {
    final int stable(int x) {
        return x + 3;
    }
}
```

Subclass không được override `stable(int)`; compiler có thêm thông tin về target. **Không phải** vì keyword `final` tự động tạo ra machine code nhanh hơn ở mọi lần gọi: JIT còn cân nhắc kích thước method, tần suất chạy, inlining budgets và profiling.

### 4.3. Exact runtime type được chứng minh từ flow

```java
static int use() {
    FixedCalculator c = new FixedCalculator();
    return c.compute(10);
}
```

Đây là method minh họa, cần đặt trong class có thể truy cập `FixedCalculator`. Trong trường hợp trên, compiler có thể suy ra exact type của `c` ở call site, dù tạm bỏ qua việc một bản build có chọn inline hay không.

Nhưng nếu viết `Base b = loadFromExternalSource();`, chưa có bằng chứng exact type. Tên kiểu tĩnh `Base` không tự khẳng định runtime type luôn đúng `Base`.

### 4.4. Sealed types trong Java 17

```java
sealed interface Token permits TextToken, NumberToken {}

final class TextToken implements Token {}

final class NumberToken implements Token {}
```

Java 17 hỗ trợ sealed classes/interfaces để giới hạn những kiểu **trực tiếp** được phép extend/implement. Đây là dữ kiện cấu trúc hữu ích, nhưng **không đủ để tuyên bố JIT chắc chắn biết một method target duy nhất**: sealed hierarchy vẫn có thể có nhiều concrete classes, non-sealed branches trong hierarchy thích hợp, và JIT policy có thể không khai thác thông tin đó trong mọi runtime.

**Đừng đồng nhất “closed hierarchy” với “monomorphic call site”.** Một sealed interface có hai implementation hoàn toàn có thể nhận cả hai types ở cùng một site.

## 5. Class Hierarchy Analysis (CHA)

**CHA** phân tích mối quan hệ giữa class/interface và những concrete method targets mà JVM **đã biết hoặc có thể chứng minh theo constraints đang quản lý**.

Giả sử:

```java
abstract class Handler {
    abstract int run(int x);
}

final class OnlyHandler extends Handler {
    @Override
    int run(int x) {
        return x * 3;
    }
}
```

Trong một thời điểm JVM chỉ đang biết `OnlyHandler` là concrete subtype của `Handler`, một lời gọi `handler.run(x)` qua `Handler` có thể **hiện đang có một concrete target duy nhất**. HotSpot có thể dùng thông tin ấy để devirtualize/inline.

### Nhưng class hierarchy có thể thay đổi

Java cho phép **dynamic class loading** theo quy tắc class loader/runtime. Một class mới được nạp sau khi code đã JIT compile có thể tạo thêm một concrete implementation.

```text
Thời điểm T1:
  Handler
     └── OnlyHandler    (unique loaded concrete target)

JIT ở T1: dùng giả định CHA → optimized call path

Thời điểm T2:
  Handler
     ├── OnlyHandler
     └── AnotherHandler (nạp sau)

JVM phải làm compiled assumptions phù hợp lại với
hierarchy mới: invalidate/deopt/recompile khi cần.
```

**Nguyên tắc an toàn:** nếu JIT tối ưu dựa trên giả định “chỉ có một concrete target **hiện được biết**”, giả định đó **không mang nghĩa bất biến suốt đời tiến trình**. HotSpot theo dõi các **compiled-code dependencies** liên quan và có thể đánh dấu nmethod không còn entrant, deoptimize hoặc biên dịch lại khi hierarchy invalidation xảy ra.

Không thể lấy một ảnh snapshot lúc T1 rồi tuyên bố JVM sẽ gọi `OnlyHandler` khi nhận object `AnotherHandler` ở T2. Nếu Java semantics yêu cầu gọi override mới, VM phải làm đúng.

### CHA khác devirtualization dựa trên type profiling

| Nguồn thông tin | Tính chất | Giới hạn |
| --- | --- | --- |
| **CHA** | Dựa vào class hierarchy và tập targets biết được | Dynamic loading có thể làm giả định cũ mất hiệu lực |
| **Runtime type profile** | Dựa trên những receiver types thực sự quan sát tại **call site** | Workload/traffic có thể thay đổi, profile có thể thiếu type hiếm |
| **Exact type proof** | Dựa vào constraints tĩnh/dataflow chắc chắn trên một path | Chỉ áp dụng nơi compiler chứng minh được |
| **Final method/class** | Ngăn override hoặc subclassing theo Java semantics phù hợp | Không tự bảo đảm compiler chọn inline |

Các nguồn thông tin **có thể được dùng phối hợp**, không phải bốn algorithms loại trừ nhau.

## 6. Type profiling: một call site có thể monomorphic hoặc polymorphic

Type profile mô tả **hành vi tại một vị trí gọi**, không đơn giản mô tả “ứng dụng có bao nhiêu implementation của interface”.

| Kiểu call site | Quan sát thường gặp | Cơ hội tối ưu |
| --- | --- | --- |
| **Monomorphic** | Site hầu như chỉ thấy một concrete receiver type | Guarded/direct devirtualization và inlining thuận lợi |
| **Bimorphic/polymorphic nhỏ** | Site thấy một số ít concrete types, có thể hai | Có thể tạo nhiều guarded paths/inlining targets |
| **Megamorphic** | Site thấy nhiều receiver types, profile không đại diện tốt cho một tập nhỏ | Generic dispatch có thể kinh tế và ổn định hơn |
| **Unprofiled/cold** | Chưa có đủ runtime evidence | Interpreter/C1 hoặc đường gọi tổng quát |

**Không có ngưỡng bất biến cho “megamorphic = đúng 3 classes”.** HotSpot có khả năng/trần ghi type profiles tùy build/flags, đồng thời quyết định inline dựa trên budget, probabilities và hotness. Một framework có hàng trăm implementation ở toàn bộ process nhưng mỗi site chỉ nhận một type vẫn có thể có **monomorphic sites**.

### Ví dụ hai call sites khác nhau

```java
static int siteA(Payment p, int x) {
    return p.calculate(x);
}

static int siteB(Payment p, int x) {
    return p.calculate(x);
}
```

Đây là các methods minh họa trong một class. Nếu `siteA` chỉ nhận `StandardPayment` còn `siteB` nhận cả hai implementation, **type profiles có thể khác** dù cả hai có cùng Java signature và cùng source-level interface call.

JIT có thể inline `siteA` và giữ dispatch ở `siteB`. Điều đó **không mâu thuẫn**: tối ưu theo call site là một thuộc tính của runtime path, không phải quyết định toàn cục cho mọi invocation của interface.

### Call site còn có thể nằm trong compiled caller sau inlining

Nếu method `route(Payment p)` được inline vào một caller khác, các compiler transformations có thể tạo những cơ hội exact type specialization mới. Vì vậy khi đọc logs, hãy xét **bối cảnh inlining tree và BCI**, không chỉ một tên method.

## 7. Guarded devirtualization và polymorphic inline caches

Khi profile nói rằng một type `FastPayment` xuất hiện phần lớn thời gian, JIT có thể dùng mô hình:

```text
if (receiver is FastPayment) {
    // direct call hoặc inline FastPayment.calculate()
} else {
    // fallback virtual/interface dispatch
    // hoặc uncommon trap → deopt/reprofile
}
```

Đây là **pseudocode**, không phải Java source thực tế HotSpot phải tạo. Quan trọng là **guard protects speculation**:

- Nếu receiver đúng type dự đoán, chạy fast path.
- Nếu receiver khác, **không được gọi nhầm** implementation.
- Nếu receiver null, phải giữ kết quả `NullPointerException` theo semantics.
- Nếu class hierarchy thay đổi, compiled dependencies phải được xử lý an toàn.
- Các exceptions/side effects của target method phải không bị thay đổi về ngữ nghĩa.

**Polymorphic Inline Cache (PIC)** là một khái niệm thường dùng cho đường dispatch có một số receiver shapes/types được lưu/kiểm tra để tăng tốc. HotSpot có cơ chế inline caches, profile-based type guards và compiled call optimizations, nhưng **không nên khẳng định mọi optimized call site được hiện thực bằng một cấu trúc PIC giống nhau**. Thuật ngữ mô tả họ kỹ thuật; machine code thật tùy VM/CPU/JDK.

### Hai target hot

Nếu site thường thấy `FastPayment` và `DiscountPayment`, VM có thể chọn logic minh họa:

```text
receiver == FastPayment klass?
  yes → optimized FastPayment path
  no  → receiver == DiscountPayment klass?
           yes → optimized DiscountPayment path
           no  → general dispatch / deoptimization
```

Bộ biên dịch **không có nghĩa vụ tạo đúng hai guards**. Nếu code size/branch prediction/inline budget không thuận lợi, nó có thể chọn generic virtual dispatch dù profile thấy ít types.

## 8. Giới hạn của giả định: tại sao cần deoptimization?

Một giả định profile có thể sai theo thời gian. Ví dụ:

- Một endpoint trước đó chỉ nhận `StandardPayment`.
- Runtime bắt đầu nhận cả `PremiumPayment` khi traffic thay đổi.
- Một plugin loader nạp implementation mới.
- Dynamic proxies hoặc generated classes tạo nhiều receiver types.
- Optimized inlining đã dự đoán một hierarchy target duy nhất, nhưng class loading làm hierarchy thay đổi.

Đó không phải bug của Java hay bằng chứng compiler biên dịch sai: **HotSpot phải có đường rút lui**.

### Uncommon trap và code invalidation

JIT có thể tạo **uncommon trap** khi một nhánh ít xảy ra hoặc một assumption không còn phù hợp. JVM có thể:

1. Dừng execution của compiled path tại điểm hợp lệ.
2. Tái dựng trạng thái bytecode frames/locals/operand stacks cần thiết.
3. Tiếp tục qua interpreter hoặc compiled code khác.
4. Cập nhật profile/trap history và biên dịch lại nếu method vẫn hot.

Mã native trước đó có thể bị đánh dấu **not entrant** để không nhận những calls mới; việc dọn bỏ compiled code cần tuân theo an toàn các thread đang thực thi.

### Guard failure không nhất thiết bằng “deopt”

Một compiler cũng có thể bố trí **fallback virtual dispatch** khi guard thất bại, không cần deopt mọi lần. Do đó thấy callsite trở nên polymorphic **không chứng minh** đã xảy ra một uncommon trap cụ thể; cần compiler diagnostics của JVM thực tế.

### Deoptimization không làm chương trình trả sai kết quả

Ví dụ:

```java
Payment p = obtainPayment();
int result = p.calculate(10);
```

Đây là đoạn trong một method; `obtainPayment()` chưa định nghĩa. Dù JIT từng quan sát phần lớn `p` là `StandardPayment`, nếu lần này nhận `PremiumPayment`, JVM vẫn phải trả **20** (theo định nghĩa `PremiumPayment` ở ví dụ trên), không phải **12**. Nếu guard nhận ra khác type, nó chọn implementation hợp lệ.

**Điểm cốt lõi:** giả định được phép **tăng tốc path thường gặp**, không được phép **thu hẹp tập hành vi Java hợp lệ**.

## 9. Class loading động và giới hạn của CHA

Trên JVM hỗ trợ dynamic loading, một class chưa được load có thể tồn tại trong classpath/JAR hoặc được tạo lúc runtime. Sự vắng mặt của nó trong hierarchy hiện tại **không chứng minh không thể xuất hiện trong tương lai**.

Các điểm lưu ý:

- CHA dựa vào những facts và dependency management mà VM có khả năng duy trì.
- Thay đổi inheritance tree có thể buộc invalidate compiled code.
- Một class được load không nhất thiết tạo instance thực sự đi vào hot call site.
- Ngược lại, một type mới có thể xuất hiện ở call site dù đã được load từ trước; khi đó type profile dùng để tối ưu có thể thay đổi.
- Class loader identity là một phần của **runtime type identity**. Cùng tên class ở hai class loaders không luôn là cùng runtime class.
- Reflection, dependency injection và plugin systems có thể làm hierarchy “mở” hơn theo thời gian.

**Không nên** vì có plugin architecture mà mặc nhiên kết luận JIT hoàn toàn không thể devirtualize. Một call site vẫn có thể monomorphic trong đa số traffic; VM dùng guards/dependency checks để bảo toàn correctness.

### Interface default methods và method resolution

Java interfaces có thể có `default` methods và những luật resolution phức tạp hơn một class-only hierarchy. HotSpot phải tuân theo method lookup/linkage của JVM, kể cả interface resolution và các errors được định nghĩa khi chương trình không hợp lệ sau thay đổi binary tương thích.

Do đó “biết class của receiver” là phần rất quan trọng nhưng **không có nghĩa một `invokeinterface` luôn được tối ưu chỉ bằng phép so một class name string**. VM còn giải quyết target method theo runtime metadata và các JVM linkage rules.

## 10. Inlining khuếch đại lợi ích của devirtualization

Giả sử compiler xác định `calculate` luôn gọi implementation:

```java
final class AddFee {
    int calculate(int x) {
        return x + 2;
    }
}

static int finalAmount(AddFee fee, int base) {
    return fee.calculate(base) * 3;
}
```

Đây là mã minh họa đặt trong một class/compilation unit hợp lệ. Nếu JIT inline method nhỏ, phép toán có thể tối ưu gần như:

```text
result = (base + 2) * 3
```

Nhưng đây **không phải native assembly đã đo**, mà chỉ là **ngữ nghĩa tính toán tương đương**. Compiler phải bảo toàn null checking nếu `fee` có thể null: gọi `fee.calculate(...)` phải ném `NullPointerException` ở đường cần thiết. Không thể tùy tiện thay lời gọi bằng biểu thức số học nếu việc thay sẽ xóa lỗi hoặc side effect quan sát được.

### Tối ưu xuyên ranh giới method

Sau inlining, JIT có thể thấy:

- Constants của caller truyền vào callee.
- Branches không cần thiết trên một hot path.
- Array bounds checks có thể chứng minh an toàn.
- Allocations không escape, tạo cơ hội scalar replacement.
- Loop computation có thể hoist/vectorize theo điều kiện.
- Giá trị trả về có thể constant-fold khi inputs cố định.

**Tuy nhiên:** Java Memory Model, volatile operations, locking, exception ordering và các side effects vẫn là ràng buộc correctness. JIT không được xóa side effect chỉ vì method bị inline.

### Devirtualization không tự làm call bằng 0 chi phí

Một guarded path có thể thêm check/branch, code cache pressure, instruction cache pressure và deoptimization work. Nếu call target nhỏ và hot, inlining có thể thắng; nếu callsite megamorphic hoặc targets quá lớn, dispatch chung có thể kinh tế hơn.

## 11. C1, C2 và warm-up: vì sao trạng thái JIT thay đổi theo thời gian?

HotSpot tiered compilation có thể cho method chạy ở interpreter rồi C1, sau đó C2 khi hot và đủ profile. Thông thường:

- **Interpreter / C1 profiling** thu thập invocation/backedge counters, type/branch data.
- **C1** có thể tạo mã nhanh để giảm overhead interpretation trong lúc vẫn profile.
- **C2** có thể sử dụng type profiles/CHA để devirtualize và inline hot calls.
- Nếu assumptions đổi, **deopt/recompile** có thể xảy ra.

Không phải mọi JIT optimization chỉ có ở C2; C1 cũng có các tối ưu và cơ chế guarded calls của nó. Nhưng C2 thường có ngân sách và cấu trúc tối ưu chuyên sâu hơn.

### Một benchmark có thể trải qua nhiều “đời” compiled code

```text
Startup:
  call site còn cold → interpreter/generic dispatch

Warm-up A:
  receiver = ClassA nhiều → profile monomorphic
  → C1/C2 có thể tạo optimized ClassA fast path

Traffic phase B:
  receiver = ClassB xuất hiện
  → guard fail/fallback hoặc deopt

Warm-up B:
  profile nhiều types hơn
  → recompile hoặc generic dispatch
```

**Không suy** kết quả performance sau 1.000 calls bằng trạng thái của cùng method sau 1 triệu calls. Compiler thresholds, queue length, code cache và CPU quotas cũng ảnh hưởng.

## 12. Java 17+ runnable: cùng một call site nhận nhiều receiver types

Để quan sát nguyên tắc, tạo file **`DevirtualizationDemo.java`**:

```java
public class DevirtualizationDemo {
    interface Operation {
        int apply(int x);
    }

    static final class PlusTwo implements Operation {
        @Override
        public int apply(int x) {
            return x + 2;
        }
    }

    static final class TimesTwo implements Operation {
        @Override
        public int apply(int x) {
            return x * 2;
        }
    }

    static final class MinusOne implements Operation {
        @Override
        public int apply(int x) {
            return x - 1;
        }
    }

    private static volatile long sink;

    // Cùng một invokeinterface call site ở bytecode của invoke.
    static int invoke(Operation operation, int value) {
        return operation.apply(value);
    }

    static long phase(Operation operation) {
        long sum = 0;
        for (int i = 0; i < 100_000; i++) {
            sum += invoke(operation, i % 10);
        }
        return sum;
    }

    public static void main(String[] args) {
        Operation plus = new PlusTwo();
        Operation times = new TimesTwo();
        Operation minus = new MinusOne();

        long first = phase(plus);
        long second = phase(times);

        int a = invoke(plus, 10);
        int b = invoke(times, 10);
        int c = invoke(minus, 10);

        sink = first + second + a + b + c;

        System.out.println("first phase: " + first);
        System.out.println("second phase: " + second);
        System.out.println("plus(10): " + a);
        System.out.println("times(10): " + b);
        System.out.println("minus(10): " + c);
        System.out.println("checksum: " + sink);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 DevirtualizationDemo.java
java DevirtualizationDemo
```

**Standard output chính xác (khi không bật JIT/GC logging):**

```text
first phase: 650000
second phase: 900000
plus(10): 12
times(10): 20
minus(10): 9
checksum: 1550041
```

### Giải thích số học

- Trong mỗi `phase`, `i % 10` cho dãy **0..9**, lặp lại 10.000 chu kỳ.
- `PlusTwo.apply(i % 10)` cho 2..11; tổng một chu kỳ là **65**; `first = 65 × 10.000 = 650.000`.
- `TimesTwo.apply(i % 10)` cho 0,2,...,18; tổng một chu kỳ **90**; `second = 900.000`.
- `PlusTwo.apply(10) = 12`; `TimesTwo.apply(10) = 20`; `MinusOne.apply(10) = 9`.
- `checksum = 650.000 + 900.000 + 12 + 20 + 9 = 1.550.041`.
- Field `volatile sink` bảo đảm assignment và read tương ứng có nghĩa quan sát được; tuy nhiên compiler **vẫn có thể thực hiện nhiều optimization hợp lệ khác**.

### Điều demo chứng minh và không chứng minh

**Chứng minh:**

- Một **interface type** có nhiều implementations hợp lệ.
- Method `invoke` có cùng source-level call site nhưng tạo kết quả phù hợp từng runtime receiver type.
- Một phase dùng một implementation nhiều lần; phase khác dùng implementation khác.
- Java semantics vẫn đúng dù JIT thay đổi chiến lược dispatch.

**Không chứng minh:**

- `invoke` chắc chắn đã được compiled ở C2 level 4.
- HotSpot chắc chắn đã dùng CHA, một guard cụ thể hay uncommon trap.
- JVM bắt buộc đi qua monomorphic → bimorphic → megamorphic theo đúng ba đoạn.
- Máy khác sẽ in cùng số JIT compilation events.
- Một time measurement ngắn là bằng chứng chi phí virtual call trong production.

Kết quả tính toán **ổn định** nhưng việc JIT có devirtualize/inlining/OSR hay không **phụ thuộc runtime**, không đoán từ số lượng vòng lặp đơn thuần.

## 13. Kiểm tra bytecode bằng javap

Chạy:

```bash
javap -c -p DevirtualizationDemo
```

Tìm method `invoke(DevirtualizationDemo.Operation, int)` (cách in tên đầy đủ phụ thuộc `javap`). Bạn sẽ thấy lời gọi `Operation.apply` thể hiện bằng **`invokeinterface`**.

Điều này xác nhận **bytecode có dynamic-dispatch semantics**. Nó **không** bác bỏ việc C1/C2 tạo machine code trực tiếp/inline. `javap` đọc classfile; nó **không** đọc code cache của JVM đã chạy một method hàng nghìn lần.

### So sánh opcode

Trên một Java class khác nếu có:

```java
static int twice(int x) {
    return x * 2;
}

static int callStatic() {
    return twice(10);
}
```

Đây là snippet method minh họa trong cùng class. `callStatic` thường dùng `invokestatic` vì method `twice` là static, không có receiver polymorphism. **Không gọi đó là thành quả devirtualization**, vì dynamic dispatch chưa từng là yêu cầu tại call site này.

## 14. Quan sát quyết định inline của HotSpot

Với HotSpot JDK 17 hỗ trợ diagnostic flags:

```bash
java -XX:+PrintCompilation DevirtualizationDemo
```

Để xem thêm quyết định inlining:

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining DevirtualizationDemo
```

Output có thể **rất dài**: JVM compile cả các methods của JDK libraries, logging xen với `System.out.println`. Các dạng thông tin bạn có thể tìm:

```text
... DevirtualizationDemo::invoke ...
... DevirtualizationDemo$PlusTwo::apply ... inline (hot)
... TypeProfile (... receiver klass ...)
... virtual call ...
... made not entrant ...
```

**Đây là những mẫu cách diễn đạt, không phải stdout cố định và không phải tất cả lines bắt buộc xuất hiện.** Một run chỉ dùng interpreter/C1 hoặc phương án optimization khác có thể không có các dòng tương ứng.

### Giải thích các dấu hiệu thường gặp

| Log fragment | Gợi ý, không là định luật |
| --- | --- |
| `inline (hot)` | JIT đã quyết định inline một target trong compilation context được in |
| `TypeProfile` / receiver class info | Compiler đang dùng/hiển thị thông tin runtime type tại một vị trí |
| `virtual call` | Call site có thể chưa được inline hoặc đường dispatch còn tổng quát |
| `made not entrant` | Một nmethod không còn nhận entry mới theo trạng thái VM |
| `made zombie` | Một trạng thái nội bộ trong lifecycle compiled code |
| Compilation level 3/4 | Tiered JIT level phù hợp nếu format log có level |
| `%` trong `PrintCompilation` | Thường liên quan OSR compilation |

**Cẩn trọng:** `PrintInlining` ghi quyết định **ở thời điểm compile một version**, không là lịch sử toàn bộ những receiver types đã từng gọi trong mọi JVM state. Một method có thể được compile lại nhiều lần.

### Vì sao output thay đổi?

- Tiered policy chọn compiler level khác.
- JVM version/hardware/compiler flags khác.
- C1/C2 compilation queue đang bận.
- Code cache đầy hoặc compiler policy hạn chế.
- Workload chưa đủ hot hoặc bị tối ưu gộp caller/callee.
- Class loading, receiver profile và timing khác.
- Startup classes/JDK library methods được compile trước, chen vào log.

**Không dùng “log phải chứa inline (hot)” làm unit test bắt buộc cho source code**. Muốn benchmark hãy đo kết quả/throughput/latency bằng công cụ phù hợp.

## 15. Chạy các chế độ để phân biệt bytecode và JIT

Các lệnh sau thử trên **những JVM processes riêng**:

```bash
java -Xint DevirtualizationDemo
java -XX:TieredStopAtLevel=1 DevirtualizationDemo
java -XX:+PrintCompilation DevirtualizationDemo
java -XX:-TieredCompilation -XX:+PrintCompilation DevirtualizationDemo
```

- `-Xint` chọn chế độ chủ yếu **interpreter-only cho Java methods**, hữu ích làm baseline correctness; thường chậm với workload tính toán.
- `TieredStopAtLevel=1` giới hạn compilation level trong HotSpot tiered policy, không bắt mọi cold method phải compile.
- `PrintCompilation` giúp quan sát compilation events.
- `-XX:-TieredCompilation` thay **JIT compilation policy**, **không** đồng nghĩa vô hiệu JIT như `-Xint`.

**Cả bốn lần chạy**, nếu JVM hỗ trợ flags và chương trình hoàn tất bình thường, output tính toán **phải giống** mục 12. Số JIT events, compiler decisions và tốc độ thì khác.

### Tắt inlining không chứng minh mọi devirtualization đều tắt

HotSpot có `-XX:-Inline` để điều chỉnh inlining trên những builds hỗ trợ. Nhưng **devirtualization và inlining là hai việc khác nhau**. Tắt inline không nhất thiết buộc mọi call site trở về generic interface dispatch: VM vẫn có thể biết target và gọi trực tiếp.

Đừng dùng `-XX:-Inline` trong production như một “cách sửa lỗi đa hình” nếu chưa có bằng chứng profiler và benchmark. Flag can thiệp rộng vào tối ưu JIT.

## 16. JIT compilation log chi tiết và machine code diagnostics

Nếu cần chứng cứ sâu hơn (và được phép tạo log file trong môi trường thí nghiệm):

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit-devirt.xml DevirtualizationDemo
```

HotSpot có thể ghi log JIT ở định dạng XML phục vụ phân tích, không phải stdout gọn như `PrintCompilation`. Mức chi tiết, tên events và công cụ đọc phụ thuộc JDK version. Một số events liên quan `uncommon_trap`, inlining, type profile hoặc dependency; **không khẳng định mọi event đã log là một deoptimization runtime thật** khi chưa phân biệt parse/compile/runtime actions.

### In assembly

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly DevirtualizationDemo
```

Phụ thuộc **hsdis** đúng JDK/OS/architecture và diagnostic setup. Nếu không có disassembler, có thể không thấy machine instructions dù JIT đã compile bình thường. Assembly còn có thể rất dài; nên dùng trên isolated test process hoặc công cụ phân tích thích hợp.

### jcmd đối với tiến trình đang chạy

```bash
jcmd -l
jcmd PID help
jcmd PID Compiler.queue
jcmd PID Compiler.codelist
jcmd PID Compiler.codecache
```

Thay `PID` bằng process ID thật, không gõ nguyên placeholder. Chương trình demo có thể kết thúc quá nhanh để attach; muốn xem live trạng thái JIT, dùng service hoặc test process tồn tại đủ lâu. `jcmd` chỉ có các commands mà binary hỗ trợ và đòi hỏi quyền attach thích hợp.

**Những lệnh này không trực tiếp nói “method X đã dùng CHA”**; chúng cung cấp bối cảnh compile/code cache, cần kết hợp logs/assembly khi muốn biết devirtualization thật.

## 17. Lời gọi qua interface trong code thực tế: không tự kết luận quá sớm

Các code bases dùng interface polymorphism rất nhiều:

- Service interfaces và dependency injection.
- Strategy/State/Command patterns.
- Plugin APIs với runtime-loaded implementations.
- Collections và iterators qua interfaces.
- Logger interfaces, adapters và generated proxies.
- ORM/session abstractions, proxy subclasses.
- Lambda/method references qua functional interfaces.

**Sai lầm phổ biến:** “Java interface luôn chậm vì virtual call”. HotSpot có type profile/CHA/inlining rất mạnh; một callsite interface có receiver type ổn định có thể được tối ưu gần direct/static code.

**Sai lầm ngược lại:** “JIT luôn tối ưu được mọi interface call”. Một site thật sự megamorphic, targets lớn, code cache pressure, latency warm-up hoặc class loading phức tạp có thể ngăn/thay đổi tối ưu.

### Framework proxy có thể làm callsite thay đổi kiểu

Một codebase có nhiều decorators/proxies khác runtime classes thực nhận. Ví dụ:

```text
Service s = JDK dynamic proxy
hoặc
Service s = concrete implementation
```

Đây là **mô hình**, không phải Java source đầy đủ. Tùy nơi caller nhận được reference, type profile có thể thấy concrete class, một proxy class hoặc nhiều classes. Điều đó ảnh hưởng khả năng inline từng đường dispatch. Nhưng **không tự suy rằng cứ có proxy là không thể inlining**.

### Tối ưu cấu trúc code nên dựa vào mục tiêu

- Ưu tiên **API clarity, testability và correct polymorphism**.
- Tránh tự thay mọi interface bằng `switch(instanceof)` chỉ để “giúp JIT”.
- Với hot path thật sự, profile trước, xác định type distribution và measured cost.
- Nếu một polymorphic site là bottleneck, cân nhắc giảm số target types, tách callsites theo đường nghiệp vụ hoặc làm dataflow exact type rõ hơn **khi vẫn giữ đúng thiết kế**.
- Benchmark end-to-end và dùng microbenchmarks có thiết kế đúng khi cần kiểm chứng cost riêng.

## 18. Compiler assumptions còn chịu những ràng buộc ngữ nghĩa khác

### Null receiver

```java
Payment p = null;
p.calculate(10);
```

Đây là đoạn trong method, sẽ ném `NullPointerException` khi thực thi lời gọi instance. Nếu JIT inline/khử dispatch, **nó vẫn phải bảo toàn kết quả exception phù hợp**, kể cả khi null check được implicit hoặc kết hợp với một kiểm tra khác.

### Side effects, exceptions và locks

Callee có thể:

- Ghi field `volatile`.
- Thực hiện `synchronized`.
- Ném checked/unchecked exceptions.
- Chạm class initialization/field access.
- Gọi native method.
- Thực hiện I/O, cập nhật dữ liệu chia sẻ.

Đích lời gọi có thể được inline hoặc gọi trực tiếp, nhưng Java Memory Model và observable behavior **không bị miễn trừ**. Compiler không được biến một interface call có side effect thành phép toán không tương đương.

### Class loader identity và visibility

Hai classes cùng binary name nhưng từ các defining class loaders khác nhau có thể là runtime types khác nhau. CHA/type profiles làm việc với **runtime class identity/metadata**, không so string class name rồi coi là cùng đích.

### Exceptions do linkage

`invokevirtual`/`invokeinterface` còn chịu các luật resolution/linking của JVM. JIT phải giữ ngữ nghĩa hợp lệ khi method resolution hoặc class loading dẫn tới các lỗi linkage theo JVM Specification. Không được “đoán” target rồi bỏ qua mọi kiểm tra cần thiết.

## 19. Devirtualization và escape analysis có quan hệ như thế nào?

**Devirtualization** biết target; **inlining** đưa callee vào caller; sau đó **escape analysis** và optimizations khác có thể thấy nhiều dữ kiện hơn.

```text
Virtual/interface call
    │
    ▼
JIT chứng minh hoặc dự đoán target (devirtualization)
    │
    ▼
Inline implementation nếu đáng giá
    │
    ▼
Có thể thấy allocation/field access xuyên method
    │
    ▼
Escape analysis / scalar replacement / constant folding
    │
    ▼
Ít calls / ít allocations / ít loads trên path thích hợp
```

Đây **không** có nghĩa “devirtualization tự động bỏ mọi object allocations”. Escape analysis phụ thuộc object có escape hay không, aliasing, safepoints, exceptions, intrinsics, size/budget và policy của JIT. Một allocation trong source có thể vẫn tồn tại trên heap.

**Lợi ích thực tiễn:** đôi khi tiết kiệm dispatch call chỉ là phần nhỏ; giá trị lớn hơn là mở đường tối ưu toàn bộ chuỗi tính toán qua nhiều method.

## 20. Hiệu năng: đừng suy trực tiếp từ số lượng virtual calls

Một site có 1 triệu virtual calls chưa chắc là bottleneck. CPU cost phụ thuộc:

- Target method có lớn hơn overhead dispatch hàng trăm lần không?
- Branch predictor có dự đoán được patterns của receiver types không?
- Call site được JIT inline trên đường nóng chưa?
- Instruction cache footprint sau inlining.
- Code cache occupancy và compilation overhead.
- Tỷ lệ khác nhau của receiver types trong production.
- GC/allocation pressure và cache locality.
- JVM warm-up/OSR/deoptimization frequency.
- CPU architecture, frequency scaling, container throttling.

### Benchmark đáng tin hơn “inlining folklore”

Với microbenchmark, dùng **JMH** hoặc harness tương đương để kiểm soát warm-up, forks, kết quả observable (tránh dead-code elimination), inputs và JVM flags. Với service, đo **throughput, p50/p95/p99 latency và CPU profiles** trong điều kiện thực.

Một trường hợp JIT devirtualization giúp rất nhiều ở một microbenchmark có thể ít ảnh hưởng end-to-end latency nếu phần lớn thời gian là network I/O/database. Đừng đổi cả public API thành concrete classes chỉ vì một lần nhìn `invokeinterface` trong `javap`.

### Warm-up có thể thay đổi receiver distribution

Nếu trong warm-up bạn chỉ dùng `MockPayment` còn production dùng `StandardPayment`, compiler có thể tối ưu theo profile không đại diện. Khi production đổi distribution, có thể thấy guard failures/deopt/recompile và tốc độ đầu giờ tải khác kỳ vọng.

Warm-up hợp lý nên phản ánh **những shapes/receiver types quan trọng của production**, nhưng vẫn cần xác nhận bằng metrics thay vì hard-code số lần gọi cố định.

## 21. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “`invokeinterface` lúc nào cũng chậm hơn `invokestatic`.” | JIT có thể devirtualize/inline interface call khi đủ dữ kiện; performance tùy path |
| “Devirtualization và inlining là cùng một việc.” | Một việc xác định callee, một việc đưa code vào caller |
| “Có interface nghĩa là không thể inline.” | Runtime profile có thể monomorphic |
| “Một interface có 20 implementations nên mọi site megamorphic.” | Polymorphism được đánh giá **theo call site** |
| “Monomorphic nghĩa là interface có đúng một implementation trong source.” | Một site có thể chỉ **quan sát** một type dù hierarchy lớn |
| “CHA thấy một target thì giả định luôn đúng mãi.” | Dynamic class loading có thể làm dependency invalid, cần deopt/invalidation |
| “Class `final` làm code luôn nhanh hơn.” | Giúp xác định target nhưng compiler không bảo đảm inline/perf thắng |
| “`sealed` bảo đảm chỉ một runtime target.” | Có thể cho phép nhiều concrete subclasses |
| “Guard fail làm JIT trả sai method.” | JVM phải dispatch/fallback/deopt đúng theo semantics |
| “Deopt là crash hoặc exception.” | Đây là cơ chế runtime chuyển về execution tổng quát |
| “`javap -c` chứng minh JIT không khử dispatch.” | `javap` chỉ hiển thị bytecode class file |
| “`PrintInlining` không có output nghĩa là JIT không hoạt động.” | Có thể logs/flags/workload/version chưa phù hợp |
| “C2 luôn devirtualize mọi hot call.” | Profile, budget, method size, code cache và policy là giới hạn |
| “Dynamic proxy ngăn JIT tối ưu mọi nơi.” | Cần quan sát receiver profile cụ thể |
| “Tắt inlining đồng nghĩa tắt devirtualization.” | Hai optimization không đồng nhất |
| “Mỗi lần JVM nhìn thấy type mới chắc chắn deopt.” | Có thể có fallback/guarded path không cần deopt |
| “Callee có side effects vẫn có thể loại bỏ tùy ý sau inline.” | Observable Java semantics phải giữ đúng |
| “Đọc Class.getName() là đủ biết class identity.” | Class loaders khác nhau có thể tạo runtime types khác |
| “JIT quyết định chỉ dựa trên source-code keyword.” | Runtime types/profiles/hierarchy/flags/CPU đều ảnh hưởng |
| “Benchmark một lần sau khi chạy là đã đo steady state.” | Warm-up và recompilation tạo nhiều pha hiệu năng khác nhau |

## 22. Bài tập có lời giải

### Bài 1 — Dispatch theo runtime receiver

Có `Payment p = new StandardPayment();` và `p.calculate(10)` theo định nghĩa mục 1.  
**Đáp án:** **12**. Variable type `Payment` không quyết định một method implementation riêng ngoài runtime receiver type.

### Bài 2 — Đổi receiver

Nếu gán `p = new PremiumPayment()` rồi gọi `p.calculate(10)`?  
**Đáp án:** **20**. JVM phải bảo toàn dynamic dispatch; JIT không được ép gọi method của StandardPayment nếu runtime type khác.

### Bài 3 — Devirtualization khác inlining

JIT biết target `StandardPayment.calculate` nhưng không inline vì method quá lớn. Có được gọi là devirtualization?  
**Đáp án:** Có thể. Nếu dispatch động được khử thành direct call thì đã devirtualize, dù còn call boundary.

### Bài 4 — Interface lớn nhưng site chỉ có một type

Interface có 12 concrete implementations. Một hot call site chỉ nhận một implementation. Site đó có phải tự động megamorphic?  
**Đáp án:** Không. Type profiling ở call site có thể monomorphic.

### Bài 5 — Hai site có cùng signature

Một site chỉ nhận `StandardPayment`; site khác nhận cả Standard và Premium. JVM có bắt buộc tối ưu giống nhau?  
**Đáp án:** Không. Callsite profiles và optimization context khác nhau.

### Bài 6 — Class final

Vì sao class `final` giúp JIT suy ra target?  
**Đáp án:** Nó không thể có subclass, giảm khả năng method bị override; nhưng không bảo đảm inline.

### Bài 7 — Sealed hierarchy

`sealed interface` có hai permitted final implementations. Chắc chắn một target cho mọi interface call?  
**Đáp án:** Không. Site có thể nhận cả hai implementations.

### Bài 8 — CHA và class loading

CHA đã tối ưu theo một concrete target rồi một subclass mới được nạp. Có được giữ code cũ không kiểm tra?  
**Đáp án:** Không nếu compiled assumption phụ thuộc hierarchy không còn hợp lệ. HotSpot phải quản lý dependency/invalidation/deoptimization hoặc phương án bảo đảm semantics khác.

### Bài 9 — Type profiling có rủi ro gì?

Warm-up toàn type A, traffic thực chuyển type B.  
**Đáp án:** Guard miss, fallback hoặc deopt/recompile có thể xảy ra; profile không phải lời hứa các future inputs chỉ có A.

### Bài 10 — Mục đích guard

Nếu JIT chỉ inline A path, tại sao cần class/type guard trong speculative case?  
**Đáp án:** Để đường thực thi nhận B không chạy nhầm method A, bảo toàn dynamic dispatch.

### Bài 11 — Null

Nếu receiver `null` và JIT inline target, có được trả số mặc định thay vì lỗi?  
**Đáp án:** Không. Phải bảo toàn `NullPointerException` theo luật JVM.

### Bài 12 — Opcode

`javap -c` thấy `invokeinterface`. Có chắc CPU phải thực hiện interface lookup mỗi call?  
**Đáp án:** Không. HotSpot JIT có thể devirtualize/inline machine code.

### Bài 13 — Static call

`invokestatic` được gọi là “khử lời gọi ảo” sau JIT có hợp lý không?  
**Đáp án:** Không theo nghĩa đang bàn; static call không yêu cầu receiver virtual dispatch.

### Bài 14 — Mã máy không còn được dùng

Nếu code bị `made not entrant`, có chứng minh JVM sai?  
**Đáp án:** Không. Đó có thể là phần bình thường của nmethod lifecycle, deoptimization/recompilation.

### Bài 15 — Cùng một method nhiều compiled versions

Một method có thể có phiên bản JIT khác nhau qua thời gian không?  
**Đáp án:** Có. C1/C2 levels, type profiles, OSR, deopt và recompilation ảnh hưởng mã đã compile.

### Bài 16 — Dữ liệu `DevirtualizationDemo`

Giá trị `first phase` trong demo mục 12?  
**Đáp án:** **650000**, do mỗi chu kỳ 0..9 cộng 2 là tổng 65, có 10.000 chu kỳ.

### Bài 17 — Phase thứ hai

Giá trị `second phase`?  
**Đáp án:** **900000**, do hai lần tổng 0..9 = 90 cho một chu kỳ, lặp 10.000 lần.

### Bài 18 — Checksum

Giá trị cuối của `sink`?  
**Đáp án:** **1550041 = 650000 + 900000 + 12 + 20 + 9**.

### Bài 19 — Không thấy log inline

JVM không in `inline (hot)` trong một lần chạy demo. Có chứng minh HotSpot không hỗ trợ devirtualization?  
**Đáp án:** Không. JIT level, hotness, compiler flags, logging và runtime policy có thể khác.

### Bài 20 — Tắt `-XX:-Inline`

Điều này có bảo đảm mọi callsite giữ generic virtual dispatch?  
**Đáp án:** Không. Tắt inline khác với tắt devirtualization; VM có thể direct call nhưng không inline.

### Bài 21 — Reflection và class loaders

Hai class cùng tên nhưng được định nghĩa bởi hai different class loaders có thể được coi là cùng runtime klass vì name giống?  
**Đáp án:** Không. Runtime class identity gắn với defining loader, không chỉ binary name.

### Bài 22 — Tối ưu API

Có nên sửa toàn bộ interface thành concrete class chỉ vì benchmark nhỏ thấy virtual call overhead?  
**Đáp án:** Không mặc định. Đo workload, xác định bottleneck, kiểm tra compiler logs và đánh giá chi phí về thiết kế trước khi đổi API.

## 23. Checklist điều tra một hot virtual call

- [ ] Xác định đúng **bytecode call site** bằng `javap -c` và JIT context, không chỉ method name.
- [ ] Phân biệt opcode `invokevirtual`/`invokeinterface`/`invokestatic`/`invokespecial`.
- [ ] Biết receiver **runtime types** nào thật sự xuất hiện tại site?
- [ ] Site monomorphic, vài types hay megamorphic trên workload thực?
- [ ] Class hierarchy hiện tại và khả năng dynamic class loading ra sao?
- [ ] Method/class có `final`, exact type hoặc sealed constraints nào?
- [ ] Biết optimized assumption dựa trên CHA hay type profile (nếu logs đủ)?
- [ ] JIT có tạo guards, direct call, inline hoặc generic dispatch không?
- [ ] Có thể xảy ra class loading invalidation/deoptimization không?
- [ ] Đã kiểm tra code/branch/exception semantics sau optimization?
- [ ] Có tách devirtualization với method inlining và escape analysis?
- [ ] Có đọc hiệu lực của `TieredCompilation` và JIT flags?
- [ ] Có quan sát `PrintCompilation`, `PrintInlining` trong môi trường test?
- [ ] Có xem code cache/compile queue nếu C2 compilation chậm?
- [ ] Đã so performance sau warm-up lẫn ngay lúc startup?
- [ ] Benchmark có đủ warm-up, forks và không bị dead-code elimination?
- [ ] Chẩn đoán có xét CPU, GC, allocations, I/O thay vì chỉ virtual call?
- [ ] Không biến JIT implementation details thành Java API correctness conditions?

## 24. Tóm tắt

**Devirtualization** tận dụng thông tin về **runtime receiver type** để tránh cost của generic dynamic dispatch ở một hot path. **CHA** dùng class hierarchy và compiled dependencies; **type profiling** dùng những concrete types xuất hiện tại từng call site. **Exact type/final semantics** cho phép những proof mạnh hơn; **speculative assumptions** cần guarded paths, fallback hoặc deoptimization khi inputs/class hierarchy thay đổi.

Khi devirtualization tạo target cụ thể, HotSpot có thể **inline** và tối ưu xuyên method; nhưng **khử dispatch ≠ inline**, và không có compiler nào phải tối ưu mọi site trong mọi tình huống. Khả năng nạp class động, polymorphism, receiver null, exception ordering và Java Memory Model đặt ranh giới mà optimized machine code **không được vượt qua**.

### Tài liệu tham khảo

- **Java Virtual Machine Specification (Java SE 17), §2.11.8 Method Invocation and Return Instructions:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.11.8
- **Java Virtual Machine Specification (Java SE 17), Chapter 6 Instruction Set:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- **Oracle JDK 17 — `java` command, `PrintCompilation` / `PrintInlining` / compiler controls:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK HotSpot — Optimizations in HotSpot JVM** (class hierarchy analysis, devirtualization, type speculation): https://cr.openjdk.org/~vlivanov/talks/2015_JIT_Overview.pdf
- **OpenJDK HotSpot C2 — `doCall.cpp`** (guarded call, CHA target, type profile, virtual/direct call decisions; source varies by release): https://github.com/openjdk/jdk/blob/jdk-17%2B35/src/hotspot/share/opto/doCall.cpp
- **OpenJDK — Integrating Profile Caching into the HotSpot Multi-Tier Compilation System** (runtime profiling, deoptimization and class hierarchy changes): https://cr.openjdk.org/~thartmann/papers/2017-ManLang-Profile_Caching.pdf
- **Java SE 17 — JLS `8.4.3.3 Final Methods và `8.1.1.2 Final Classes:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html
- **OpenJDK JEP 197 — Segmented Code Cache:** https://openjdk.org/jeps/197/

**Thông điệp cuối:** không nên sợ interface vì một opcode `invokeinterface`, cũng không nên tin rằng C2 sẽ luôn biến mọi lời gọi ảo thành direct inline. **Hãy đo profile của chính call site, kiểm tra compiler decisions trên đúng HotSpot/JDK và luôn giữ ranh giới giữa giả định tối ưu với Java semantics bắt buộc.**