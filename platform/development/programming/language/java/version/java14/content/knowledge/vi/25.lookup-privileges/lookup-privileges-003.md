# previousLookupClass khi chuyển Lookup qua mô-đun trong Java

> **Phạm vi:** Bài thuộc **Java 14 → Quyền Lookup**, trọng tâm là `java.lang.invoke.MethodHandles.Lookup.previousLookupClass()` khi một `Lookup` được chuyển (*teleport*) giữa các Java modules. Phương thức `previousLookupClass()` có từ **Java 14** và vẫn được hỗ trợ trong Java SE 17/21/25. Ví dụ dùng **Java 17+**, Java Platform Module System (JPMS) và API `MethodHandles` chính thức, không dùng preview hoặc kỹ thuật mở encapsulation lỗi thời.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác biệt giữa `lookupClass()` và `previousLookupClass()`; hiểu vì sao `null` là kết quả bình thường.
2. Xác định tác động của `Lookup.in(Class<?>)` và `MethodHandles.privateLookupIn(Class<?>, Lookup)` lên **lookup class**, **previous lookup class** và **lookup modes**.
3. Phân biệt teleport **trong cùng module**, **sang module thứ hai**, **trong module thứ hai**, **quay về module cũ** và **sang module thứ ba**.
4. Nêu chính xác quyền `MODULE` bị mất khi teleport qua biên giới module; `Lookup.in` không thể làm tăng quyền.
5. Hiểu tại sao `PUBLIC` ở một lookup đã teleport phải kiểm tra **readability và exports từ cả module hiện tại lẫn module trước đó**.
6. Phân biệt `exports` và `opens`, giải thích điều kiện gọi `privateLookupIn` xuyên module và lý do lookup có `PRIVATE` nhưng không còn `MODULE` không thể tiếp tục xin một private lookup khác.
7. Nhận biết trường hợp đặc biệt của `MethodHandles.publicLookup()` và mode `UNCONDITIONAL`: `previousLookupClass()` vẫn bằng `null`.
8. Viết chương trình Java 17+ kiểm tra `lookupModes()`, quyền truy cập public/private và trường hợp mất quyền khi đi qua module thứ ba.
9. Dùng cơ chế này để thiết kế framework, thư viện runtime hoặc plugin có **nguyên tắc quyền tối thiểu**, tránh vô tình chia sẻ một lookup đặc quyền.

**Ghi nhớ trước:** `previousLookupClass()` **không phải** lịch sử đầy đủ các class đã đi qua, cũng **không phải** class loader trước đó. Nó ghi nhận **lookup class ở module khác mà Lookup hiện tại vừa teleport từ đó**, theo quy tắc của JDK. Có thể bằng `null` ngay cả khi một `Lookup` được tạo hoặc chuyển sang lớp khác.

## 2. Lookup là «năng lực tra cứu thành viên», không chỉ là Class

`MethodHandles.Lookup` được dùng để tạo `MethodHandle` hoặc `VarHandle` khi cần kiểm tra quyền truy cập thành viên. Một lookup mang ít nhất ba thông tin:

- **`lookupClass()`:** lớp đứng ở vai trò ngữ cảnh tra cứu hiện tại.
- **`previousLookupClass()`:** lớp ở **module khác** trong bước teleport trước, hoặc `null` khi không có ngữ cảnh như vậy.
- **`lookupModes()`:** bit mask biểu thị những mức truy cập còn được phép, chẳng hạn `PUBLIC`, `PRIVATE`, `PACKAGE`, `MODULE`, `UNCONDITIONAL`.

Một lookup còn chịu các điều kiện của JPMS và Java visibility: class/module hiện tại có đọc module kia không, package có `exports` hoặc `opens` đúng đối tượng không, thành viên có public/private không.

Ví dụ tạo lookup tại một class:

```java
import java.lang.invoke.MethodHandles;

class Example {
    static void inspect() {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        System.out.println(lookup.lookupClass() == Example.class);
        System.out.println(lookup.previousLookupClass() == null);
    }
}
```

Đây là **class minh họa**, chưa có `main` nên không phải chương trình tự chạy. Khi `MethodHandles.lookup()` được gọi trực tiếp trong `Example.inspect()`, nó tạo lookup cho `Example.class`; `previousLookupClass()` lúc này là `null`.

**Khác với reflection thông thường:** `Class.getDeclaredMethods()` trả metadata về các phương thức, còn `Lookup.findStatic`/`findVirtual` tạo method handles **sau khi kiểm tra quyền** của lookup. Một method handle được tạo hợp lệ có thể được chia sẻ để gọi sau; việc tạo handle mới và việc gọi handle đã tạo là hai bước khác nhau.

### 2.1. Đừng nhầm ba khái niệm

| Thuộc tính | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| `lookup.lookupClass()` | «Lookup đang đại diện class nào?» | `target.api.Target.class` |
| `lookup.previousLookupClass()` | «Trước bước chuyển qua module hiện tại, lookup đại diện class ở module nào?» | `origin.app.Main.class` |
| `lookup.lookupModes()` | «Lookup còn những lớp quyền nào?» | `PUBLIC` có, `MODULE` mất |
| `lookup.lookupClass().getModule()` | «Lookup class hiện thuộc module nào?» | `m.target` |
| `lookup.previousLookupClass().getModule()` khi không null | «Class trước thuộc module nào?» | `m.origin` |

Một `Class<?>` **không tự cấp quyền**. Hai `Lookup` cùng trả `lookupClass() == Target.class` vẫn có thể khác hẳn `lookupModes()` và `previousLookupClass()`, dẫn đến tập thành viên được phép truy cập khác nhau.

## 3. Vì sao Java cần `previousLookupClass`?

Trong Java trước khi có module system, kiểm tra truy cập chủ yếu dựa vào class/package và class loader. **JPMS** bổ sung các quy tắc:

- Module **M0** có `requires M1` để đọc M1.
- Module **M1** `exports p` hoặc `exports p to M0` để cho phép kiểu public trong package `p` được nhìn thấy.
- Module **M1** `opens p to M0` để cho phép deep reflection vào package `p` khi các điều kiện khác thỏa.
- Một method handle được tạo bằng lookup từ M0 không thể mặc nhiên trở thành một lookup đặc quyền của M1.

Một lookup có thể «teleport» từ lớp `C` của M0 sang lớp `D` của M1. Khi đó:

```text
Trước:
Lookup { lookupClass=C thuộc M0,
         previousLookupClass=null,
         modes=quyền của C }

            |
            | lookup.in(D.class) -- chuyển sang module khác
            v

Sau:
Lookup { lookupClass=D thuộc M1,
         previousLookupClass=C thuộc M0,
         modes=bị thu hẹp (mất MODULE, thường còn PUBLIC) }
```

Nếu chỉ lưu `D.class` và bỏ nguồn gốc `C.class`, lookup đã chuyển có thể kiểm tra public access hoàn toàn theo M1 mà quên ràng buộc từ M0. `previousLookupClass` cho phép JDK áp dụng quy tắc **hai phía cùng đọc/nhìn thấy** ở những lookup xuyên module có `PUBLIC`.

**Định nghĩa ngắn:** `previousLookupClass()` là thông tin ngữ cảnh quyền truy cập của lookup đã teleport, chứ không phải một công cụ trace hoặc call stack.

## 4. Nguồn tạo Lookup: giá trị previous ban đầu

| Cách tạo | `lookupClass()` | `previousLookupClass()` | Đặc điểm |
| --- | --- | --- | --- |
| `MethodHandles.lookup()` | Class của **caller** trực tiếp | `null` | Có quyền tương ứng caller, thường full privilege trong lookup gốc. |
| `MethodHandles.publicLookup()` | Lookup class của public lookup | `null` | Có mode `UNCONDITIONAL`; phục vụ các public types trong packages export vô điều kiện. |
| `lookup.in(T.class)` trong **cùng module** | `T.class` | Giữ previous cũ (có thể `null`) | Quyền có thể giảm theo class/nest/package, nhưng không tăng. |
| `lookup.in(T.class)` sang **module khác** | `T.class` | Lookup class cũ (trừ trường hợp `UNCONDITIONAL`) | Mất `MODULE`; áp dụng cross-module access checks. |
| `privateLookupIn(T.class, caller)` trong **cùng module** | `T.class` | `null` | Có thể cấp private access theo hợp đồng và điều kiện caller. |
| `privateLookupIn(T.class, caller)` sang **module khác** | `T.class` | Lookup class của caller | Cần `PRIVATE + MODULE`, readability và `opens`; kết quả mất `MODULE`. |

**Điểm tinh tế:** `MethodHandles.lookup()` không nhận một `Class<?>` để tự nhận quyền của class tùy ý. Nó là **caller-sensitive**: quyền của lookup gốc gắn với caller thực. Đừng viết một helper công cộng `return MethodHandles.lookup()` rồi cho rằng helper có thể tạo full-privilege lookup cho mọi class truyền vào.

### 4.1. «Previous» không có nghĩa «phương thức trước đó»

Một codebase có thể gọi:

```java
Lookup l0 = MethodHandles.lookup();     // Ở lớp C
Lookup l1 = l0.in(D.class);             // D cùng module C
Lookup l2 = l1.in(E.class);             // E thuộc module khác
```

Nếu `C` và `D` cùng module, `l1.previousLookupClass()` vẫn `null`; sau teleport sang module của `E`, `l2.previousLookupClass()` là **`D.class`**, không phải `C.class`.

Điều này làm rõ từ «previous» chỉ **lookup class trực tiếp trước lần đổi module**, không phải class tạo lookup từ ban đầu. Các bước chuyển **trong cùng module** có thể thay đổi lớp lookup hiện tại trước khi xảy ra bước xuyên module.

## 5. Quy tắc `Lookup.in(Class<?>)` trong cùng module

Giả sử hai lớp `C` và `D` thuộc module M1:

```java
Lookup changed = original.in(D.class);
```

Kết quả:

- `changed.lookupClass() == D.class`.
- `changed.previousLookupClass() == original.previousLookupClass()`.
- Nếu không có previous trước đó, kết quả vẫn `null`.
- `MODULE` có thể được giữ **nếu lookup ban đầu có mode này**; việc đổi lớp trong cùng module **không tự loại `MODULE`**.
- `ORIGINAL` bị mất nếu lookup class thực sự đổi.
- `PRIVATE`, `PACKAGE` và `PROTECTED` có thể bị giảm khi đổi nest, package hoặc quan hệ kế thừa; **không nên suy ra mọi quyền được giữ nguyên** chỉ vì cùng module.
- Quyền không tăng; một lookup đã bị giới hạn không thể gọi `in` để lấy lại các quyền đã mất.

**Ví dụ:** Lookup từ `C` trong package `a` chuyển sang `D` trong package `b` của cùng module có thể giữ `MODULE` nhưng mất quyền truy cập package-private members của `a`. `previousLookupClass` vẫn `null` (nếu ban đầu null), bởi thay đổi này **không đi qua ranh giới module**.

## 6. Quy tắc khi chuyển qua module khác bằng `Lookup.in`

Giả sử:

```text
Module M0: class C  -- requires -->  Module M1: public class D
Module M1: exports package chứa D cho M0
```

Với lookup gốc `cLookup`:

```java
Lookup dLookup = cLookup.in(D.class);
```

Nếu `D` có thể được truy cập theo điều kiện JPMS, kết quả thông thường là:

1. `dLookup.lookupClass() == D.class`.
2. `dLookup.previousLookupClass() == C.class` khi `cLookup.lookupClass() == C.class`.
3. `MODULE` **bị loại bỏ**.
4. `PRIVATE`/`PACKAGE`/`PROTECTED` không được mang theo để vượt module theo `Lookup.in` thông thường.
5. `PUBLIC` có thể được giữ và quyền public bị kiểm tra dựa vào **hai module**, không chỉ module mới.
6. Nếu target class vốn không accessible cho lookup, lookup kết quả có thể mất **tất cả access modes** (giá trị `0`).

**Không phải quyền `public` của class D cấp quyền public cho mọi thứ trong module M1.** Lookup phải tính tới `readability`, `exports`, tên class và member visibility, đồng thời với previous module nếu có.

### 6.1. Bảng theo dõi khi teleport nhiều bước

Giả định `C∈M0`, `D∈M1` và `E∈M2`, ba module khác nhau, các class target đều được truyền hợp lệ:

| Bước | Lookup class mới | Previous lookup class mới | Quyền quan trọng |
| --- | --- | --- | --- |
| `MethodHandles.lookup()` tại C | C (M0) | `null` | Quyền gốc của C |
| `l0.in(C2.class)`, C2 thuộc M0 | C2 (M0) | `null` | Không tăng; `MODULE` có thể giữ |
| `l0.in(D.class)`, D thuộc M1 | D (M1) | C (M0) | Mất `MODULE`, chỉ còn mức public phù hợp |
| `l1.in(D2.class)`, D2 thuộc M1 | D2 (M1) | C (M0) | Previous **giữ nguyên**, quyền không tăng |
| `l1.in(E.class)`, E thuộc M2 | E (M2) | D (M1) | **Ba module khác nhau → mất toàn bộ access modes** |
| `l1.in(C2.class)`, quay về module M0 | C2 (M0) | D (M1) | Có thể giữ một phần `PUBLIC` nếu target accessible; không lấy lại full privilege |

**Điểm đặc biệt:** «Mất toàn bộ quyền khi tới module thứ ba» là quy tắc **teleport sang lớp trong module thứ ba** khi lookup class hiện tại, previous lookup class và target class thuộc ba module khác nhau. Nó **không** nói rằng lookup ở M1 đã có previous M0 tuyệt đối không thể **tìm public method trong M2**. Hai thao tác `lookup.findStatic(M2Class...)` và `lookup.in(M2Class.class)` là khác nhau; phần 9 làm rõ.

### 6.2. Quy tắc `previousLookupClass` của `in` chính xác

Theo Javadoc Java 17/25, giá trị previous mới được chọn theo thứ tự:

1. Nếu lookup kết quả có `UNCONDITIONAL` → previous = `null`.
2. Nếu lookup class mới **cùng module** với lookup class cũ → giữ previous của lookup cũ.
3. Nếu lookup class mới **khác module** với lookup class cũ → previous = lookup class cũ.

Sau đó các access checks và khả năng `lookupModes` được áp dụng; không phải cứ có previous thì lookup còn quyền truy cập nào đó. **`previousLookupClass()!=null` và `lookupModes()==0` hoàn toàn có thể cùng đúng.**

## 7. Trường hợp đặc biệt `publicLookup()` và `UNCONDITIONAL`

`MethodHandles.publicLookup()` tạo lookup công cộng với mode `UNCONDITIONAL`. Mode này cho phép truy cập public types trong package được **exports vô điều kiện**, mà không cần mô hình đọc module giống một lookup `PUBLIC` thông thường.

```java
var publicOnly = MethodHandles.publicLookup();
var moved = publicOnly.in(java.util.logging.Logger.class);

System.out.println(moved.previousLookupClass() == null);
```

Đây là **snippet trong method**, và kết quả là `true` khi chạy trên JDK hỗ trợ. Đổi lookup class của public lookup không biến nó thành lookup sở hữu module `java.logging`, cũng không làm previous trở thành lớp nào đó của ứng dụng.

**Phân biệt:**

| Mode | Ý nghĩa khái quát |
| --- | --- |
| `PUBLIC` | Public access theo phép kiểm tra readability/exports với lookup class, và previous lookup class nếu có. |
| `UNCONDITIONAL` | Public access tới loại public trong package export vô điều kiện; previous = `null` khi lookup kết quả giữ mode này. |
| `MODULE` | Quyền module-local ở lookup hiện tại; bị bỏ khi teleport qua module khác. |
| `PRIVATE` | Khả năng truy cập private members trong phạm vi hợp lệ; không đồng nghĩa tự có `MODULE`. |
| `ORIGINAL` | Lookup được tạo theo ngữ cảnh origin có quyền đặc thù; không thể phục hồi bằng `in` sau khi mất. |

**Không nên gọi `publicLookup()` là «lookup có tất cả quyền public của module nào cũng được phép».** Nó vẫn bị giới hạn bởi `exports`, kiểu thành viên và đặc tính `UNCONDITIONAL`. Các package chỉ `exports ... to ...` (qualified exports) không trở thành public toàn cục vì lookup này.

## 8. Chương trình độc lập 1: quan sát trước/sau teleport với JDK modules

Ví dụ đầu tiên **không cần tạo ba module riêng**. Ta tạo lookup trong một class thuộc **unnamed module** (chạy từ classpath), chuyển tới hai class public có sẵn trong JDK:

- `java.util.logging.Logger` ở module `java.logging`;
- `java.sql.DriverManager` ở module `java.sql`.

Cùng với unnamed module của chương trình, đây là **ba module khác nhau**.

Lưu file **`LookupHistoryDemo.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.util.logging.Logger;
import java.sql.DriverManager;

public class LookupHistoryDemo {
    private static final class Local {}

    private static boolean has(MethodHandles.Lookup lookup, int flag) {
        return (lookup.lookupModes() & flag) != 0;
    }

    public static void main(String[] args) {
        MethodHandles.Lookup original = MethodHandles.lookup();

        // Vẫn trong unnamed module của LookupHistoryDemo.
        MethodHandles.Lookup sameModule = original.in(Local.class);

        // Chuyển từ unnamed module tới module java.logging.
        MethodHandles.Lookup inLogging =
                original.in(Logger.class);

        // Từ java.logging chuyển tiếp sang module thứ ba: java.sql.
        MethodHandles.Lookup inSql =
                inLogging.in(DriverManager.class);

        MethodHandles.Lookup unconditional =
                MethodHandles.publicLookup().in(Logger.class);

        System.out.println("original-previous-null="
                + (original.previousLookupClass() == null));
        System.out.println("same-module-previous-null="
                + (sameModule.previousLookupClass() == null));
        System.out.println("same-module-has-MODULE="
                + has(sameModule, MethodHandles.Lookup.MODULE));

        System.out.println("logging-class="
                + inLogging.lookupClass().getName());
        System.out.println("logging-previous-is-original="
                + (inLogging.previousLookupClass()
                        == LookupHistoryDemo.class));
        System.out.println("logging-has-PUBLIC="
                + has(inLogging, MethodHandles.Lookup.PUBLIC));
        System.out.println("logging-has-MODULE="
                + has(inLogging, MethodHandles.Lookup.MODULE));

        System.out.println("sql-previous-is-logger="
                + (inSql.previousLookupClass() == Logger.class));
        System.out.println("sql-modes=" + inSql.lookupModes());

        System.out.println("unconditional-previous-null="
                + (unconditional.previousLookupClass() == null));
        System.out.println("unconditional-has-mode="
                + has(unconditional,
                        MethodHandles.Lookup.UNCONDITIONAL));
    }
}
```

Biên dịch và chạy bằng **JDK 17+**:

```bash
javac --release 17 LookupHistoryDemo.java
java --add-modules java.logging,java.sql LookupHistoryDemo
```

`--add-modules` bảo đảm hai JDK modules được resolve khi chạy trên những runtime có cả hai module; với một JDK đầy đủ, chúng thông thường đã khả dụng. Nếu chạy trên custom runtime không chứa chúng, phải đưa module vào runtime image trước.

**Stdout dự kiến chính xác:**

```text
original-previous-null=true
same-module-previous-null=true
same-module-has-MODULE=true
logging-class=java.util.logging.Logger
logging-previous-is-original=true
logging-has-PUBLIC=true
logging-has-MODULE=false
sql-previous-is-logger=true
sql-modes=0
unconditional-previous-null=true
unconditional-has-mode=true
```

Các kết luận về `previousLookupClass`, `PUBLIC`, `MODULE`, `UNCONDITIONAL` và `sql-modes=0` đã được đối chiếu trực tiếp trên **JDK 24** bằng thí nghiệm tương đương sử dụng `MethodHandles.lookup()` từ unnamed module; đây là ngữ nghĩa được Javadoc Java 17/25 mô tả.

**Giải thích:**

1. `original` do `MethodHandles.lookup()` ở `LookupHistoryDemo` tạo, previous = `null`.
2. `sameModule` chuyển sang nested class `Local` trong **cùng unnamed module**, nên previous vẫn `null` và `MODULE` vẫn có.
3. `inLogging` chuyển lookup class sang `Logger` thuộc `java.logging`: previous giờ là **`LookupHistoryDemo.class`**; `PUBLIC` được giữ, `MODULE` bị mất.
4. `inSql` chuyển sang **module thứ ba** (so với module hiện tại và module previous): previous là **`Logger.class`**, nhưng lookup modes trở thành **`0`**.
5. `unconditional` bắt đầu từ `publicLookup()`; sau `in(Logger.class)` nó vẫn không có previous và vẫn mang mode `UNCONDITIONAL`.

**Không nhầm kết quả `sql-previous-is-logger=true` với quyền được phép truy cập private member của Logger.** Previous chỉ là thông tin ngữ cảnh; `inSql.lookupModes()==0` cho biết lookup đã mất mọi năng lực tạo method handle có kiểm tra quyền.

## 9. Bài toán tinh tế: quyền PUBLIC của hai module là giao nhau

Nếu một `Lookup` từ **M0** teleport sang **M1**, nó mang `lookupClass∈M1` và `previousLookupClass∈M0`. Khi tạo method handle tới public type/member, access check tính theo **cả M0 và M1**.

Tưởng tượng một module **M2** chứa class public `E`:

- M0 **đọc** M2.
- M1 **đọc** M2.
- Package của E trong M2 **exports** tới cả M0 và M1.

Khi đó một lookup đang ở M1 nhưng mang previous M0 có thể **find** public method của E nếu tất cả điều kiện thích hợp được đáp ứng.

Tuy nhiên:

```java
Lookup asE = lookupFromM1WithPreviousM0.in(E.class);
```

là **một lần teleport tiếp** từ M1 sang module thứ ba M2, nên kết quả **mất mọi access modes**, dù `findStatic(E.class, ...)` từ lookup trước đó có thể vẫn thành công. Đây là ranh giới bảo vệ chống việc đi xuyên nhiều module để mở rộng quyền.

### 9.1. Bảng phân biệt

| Thao tác | Điều xảy ra |
| --- | --- |
| `lookup.findStatic(E.class, "m", type)` | Tạo method handle sau khi kiểm tra accessibility của **member E.m** đối với lookup hiện có; lookup class **không thay đổi**. |
| `lookup.in(E.class)` | Tạo **lookup mới** với lookup class E; đổi previous theo quy tắc teleport; nếu E thuộc module thứ ba có thể mất toàn bộ quyền. |
| `lookup.findClass("p.E")` | Tra cứu class theo lookup class, loader và quyền truy cập tương ứng; không phải cách «nâng cấp» lookup. |
| `MethodHandles.privateLookupIn(E.class, lookup)` | Yêu cầu quyền private mới, điều kiện chặt hơn `in`; cần `MODULE + PRIVATE` và JPMS `reads/opens`. |

**Quy tắc thực hành:** Dùng `findStatic/findVirtual` từ lookup có quyền phù hợp nếu chỉ cần public method; không gọi `in` sang một module thứ ba «cho chắc» rồi bất ngờ mất quyền.

## 10. `privateLookupIn`: teleport qua module và giữ PRIVATE theo điều kiện chặt

`MethodHandles.privateLookupIn(Target.class, callerLookup)` có thể tạo lookup đủ quyền để truy cập private members của `Target`. Nó **không** giống `callerLookup.in(Target.class)`.

Để xin private lookup sang **module M1 từ caller module M0**:

1. `callerLookup` có cả `PRIVATE` và `MODULE`: tức có **full privilege** cần thiết cho phương thức này.
2. M0 **reads** M1 theo module graph.
3. M1 **opens** package chứa Target tới M0 (hoặc mở vô điều kiện).
4. Target là loại class hợp lệ; không phải primitive, void hay array class.

Nếu tất cả điều kiện thỏa:

- `result.lookupClass() == Target.class`;
- `result.previousLookupClass() == callerLookup.lookupClass()`;
- `result` có **`PRIVATE`** theo hợp đồng;
- `result` **không còn `MODULE`** vì đã teleport xuyên module;
- `result` cũng không có `ORIGINAL`.

**Hệ quả quan trọng:** Một private lookup thu được ở module mới có thể truy cập private member của target, nhưng vì đã **mất `MODULE`**, nó **không thể được dùng để gọi `privateLookupIn` sang module thứ ba nhằm tiếp tục leo thang quyền**. Với `privateLookupIn`, lỗi do thiếu quyền/truy cập thường là `IllegalAccessException`, không nhất thiết là `InaccessibleObjectException` của Core Reflection.

### 10.1. `exports` chưa đủ để tạo private lookup

Nếu target module chỉ có:

```java
module m.target {
    exports target.api;
}
```

thì public types có thể truy cập theo quy tắc `exports`, nhưng điều đó **không mở private members cho module khác**. Để cho `m.origin` deep reflection đúng package, thêm:

```java
module m.target {
    exports target.api;
    opens target.api to m.origin;
}
```

Các snippets module trên **là minh họa**, phụ thuộc mô-đun/thư mục source thực tế. Trong ví dụ hoàn chỉnh ở phần 11, module `m.target` còn `requires m.third` để minh họa phép giao readability.

**Không thêm `opens ... to ALL-UNNAMED` vào `module-info.java` như thể đó là cú pháp module declaration.** `--add-opens module/package=ALL-UNNAMED` là lựa chọn launcher có tình huống sử dụng riêng; module descriptor dùng `opens package [to module,...]`. Khi biết module đích, ưu tiên khai báo qualified opens để không mở rộng quyền không cần thiết.

## 11. Ví dụ modular hoàn chỉnh: ba module và các mức quyền khác nhau

Ví dụ này dùng **ba named modules** để quan sát rõ:

- Một lookup gốc trong `m.origin`;
- Teleport sang `m.target` và giữ `previousLookupClass = Main.class`;
- Một public method trong module thứ ba `m.third` có thể được tìm bằng lookup trước khi teleport, vì **cả m.origin và m.target đều reads m.third**;
- Teleport hẳn sang lớp ở `m.third` làm mất toàn bộ modes;
- `privateLookupIn` sang `m.target` thành công nhờ qualified `opens`, nhưng lookup đó không còn `MODULE` để xin private lookup tiếp.

Cây thư mục:

```text
src/
  m.third/
    module-info.java
    third/api/Third.java
  m.target/
    module-info.java
    target/api/Target.java
  m.origin/
    module-info.java
    origin/app/Main.java
```

### 11.1. Module thứ ba `m.third`

File **`src/m.third/module-info.java`**:

```java
module m.third {
    exports third.api;
}
```

File **`src/m.third/third/api/Third.java`**:

```java
package third.api;

public final class Third {
    public static String hello() {
        return "THIRD_OK";
    }
}
```

### 11.2. Module đích `m.target`

File **`src/m.target/module-info.java`**:

```java
module m.target {
    requires m.third;
    exports target.api;
    opens target.api to m.origin;
}
```

File **`src/m.target/target/api/Target.java`**:

```java
package target.api;

public final class Target {
    public static String hello() {
        return "PUBLIC_OK";
    }

    private static String secret() {
        return "PRIVATE_OK";
    }

    public static final class Sibling {}
}
```

Giải thích descriptor:

- `requires m.third` làm `m.target` đọc module thứ ba.
- `exports target.api` cho phép các module đọc `m.target` dùng public `Target`.
- `opens target.api to m.origin` cho phép **m.origin** deep reflection vào package này, nếu lookup gốc đáp ứng điều kiện.
- `secret()` vẫn **private**: chỉ lookup có quyền phù hợp mới tạo được method handle gọi nó.
- `Sibling` là class public trong cùng module để minh họa teleport **trong module hiện tại** không đổi previous.

### 11.3. Module nguồn `m.origin`

File **`src/m.origin/module-info.java`**:

```java
module m.origin {
    requires m.target;
    requires m.third;
}
```

Vì cả `m.origin` và `m.target` đều đọc `m.third`, lookup đang ở `m.target` với previous ở `m.origin` có thể tạo handle cho public method ở `m.third` khi package được export vô điều kiện.

File **`src/m.origin/origin/app/Main.java`**:

```java
package origin.app;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

import target.api.Target;
import third.api.Third;

public class Main {
    private static final class Local {}

    private static boolean has(MethodHandles.Lookup l, int mode) {
        return (l.lookupModes() & mode) != 0;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup root = MethodHandles.lookup();

        // Cùng module m.origin.
        MethodHandles.Lookup same = root.in(Local.class);

        // m.origin -> m.target: previous trở thành Main.
        MethodHandles.Lookup cross = root.in(Target.class);

        // Vẫn ở m.target: previous vẫn là Main.
        MethodHandles.Lookup crossSibling =
                cross.in(Target.Sibling.class);

        // m.target -> m.third: ba module khác nhau.
        MethodHandles.Lookup third = cross.in(Third.class);

        // Mục tiêu deep reflection: m.target mở target.api cho m.origin.
        MethodHandles.Lookup deep =
                MethodHandles.privateLookupIn(Target.class, root);

        MethodHandles.Lookup publicMove =
                MethodHandles.publicLookup().in(Target.class);

        System.out.println("origin-prev-null="
                + (root.previousLookupClass() == null));
        System.out.println("same-prev-null="
                + (same.previousLookupClass() == null));
        System.out.println("same-has-module="
                + has(same, MethodHandles.Lookup.MODULE));

        System.out.println("cross-prev-origin="
                + (cross.previousLookupClass() == Main.class));
        System.out.println("cross-has-public="
                + has(cross, MethodHandles.Lookup.PUBLIC));
        System.out.println("cross-has-module="
                + has(cross, MethodHandles.Lookup.MODULE));
        System.out.println("sibling-prev-origin="
                + (crossSibling.previousLookupClass() == Main.class));

        MethodHandle visible = cross.findStatic(
                Target.class, "hello",
                MethodType.methodType(String.class));
        System.out.println("public-call="
                + (String) visible.invokeExact());

        // findStatic ở module thứ ba không cần đổi lookupClass.
        MethodHandle other = cross.findStatic(
                Third.class, "hello",
                MethodType.methodType(String.class));
        System.out.println("third-public-call="
                + (String) other.invokeExact());

        System.out.println("third-prev-target="
                + (third.previousLookupClass() == Target.class));
        System.out.println("third-modes=" + third.lookupModes());

        System.out.println("deep-prev-origin="
                + (deep.previousLookupClass() == Main.class));
        System.out.println("deep-has-private="
                + has(deep, MethodHandles.Lookup.PRIVATE));
        System.out.println("deep-has-module="
                + has(deep, MethodHandles.Lookup.MODULE));

        MethodHandle hidden = deep.findStatic(
                Target.class, "secret",
                MethodType.methodType(String.class));
        System.out.println("private-call="
                + (String) hidden.invokeExact());

        boolean retryFailed = false;
        try {
            MethodHandles.privateLookupIn(Third.class, deep);
        } catch (IllegalAccessException expected) {
            retryFailed = true;
        }
        System.out.println("re-private-fails=" + retryFailed);

        System.out.println("public-prev-null="
                + (publicMove.previousLookupClass() == null));
        System.out.println("public-unconditional="
                + has(publicMove,
                        MethodHandles.Lookup.UNCONDITIONAL));
    }
}
```

### 11.4. Biên dịch và chạy

Đặt đúng sáu file theo cây `src/` ở trên. Mở terminal tại thư mục chứa `src` và tạo output folder `mods`.

Trên Linux/macOS:

```bash
mkdir -p mods

javac --release 17 --module-source-path src \
  -d mods -m m.origin,m.target,m.third

java --module-path mods \
  --module m.origin/origin.app.Main
```

Trên Windows PowerShell, tạo folder:

```powershell
New-Item -ItemType Directory -Force -Path mods

javac --release 17 --module-source-path src -d mods -m m.origin,m.target,m.third

java --module-path mods --module m.origin/origin.app.Main
```

**Stdout kỳ vọng trên JDK 17+ phù hợp:**

```text
origin-prev-null=true
same-prev-null=true
same-has-module=true
cross-prev-origin=true
cross-has-public=true
cross-has-module=false
sibling-prev-origin=true
public-call=PUBLIC_OK
third-public-call=THIRD_OK
third-prev-target=true
third-modes=0
deep-prev-origin=true
deep-has-private=true
deep-has-module=false
private-call=PRIVATE_OK
re-private-fails=true
public-prev-null=true
public-unconditional=true
```

**Lưu ý mức kiểm chứng:** Kết quả tương ứng quy tắc public/private/cross-module của Javadoc Java 17/25. Quy tắc gốc, đổi sang module thứ hai, module thứ ba và ngoại lệ `UNCONDITIONAL` đã được chạy thử trên JDK 24 với JDK modules. Mẫu ba **named modules** là ví dụ biên dịch theo cấu trúc JPMS đã chỉ rõ; nên chạy nguyên các lệnh ở trên trên JDK của dự án để xác minh môi trường đóng gói/module-path thực tế.

### 11.5. Giải thích kết quả đặc biệt

- `cross-prev-origin=true`: teleport `m.origin → m.target`; previous là `Main` ở module nguồn.
- `cross-has-module=false`: mất quyền `MODULE` khi vượt biên giới module.
- `sibling-prev-origin=true`: đổi class `Target → Target.Sibling` trong cùng module `m.target` giữ previous `Main`.
- `public-call=PUBLIC_OK`: lookup đã teleport còn đủ quyền public đối với method public ở package được export.
- `third-public-call=THIRD_OK`: lookup **chưa teleport sang module thứ ba**, chỉ tìm public method của class ở đó. Cả `m.origin` và `m.target` đọc `m.third` và `third.api` được export, nên access check có thể thành công.
- `third-modes=0`: khi thực sự gọi `cross.in(Third.class)`, lookup class, previous và target nằm ở ba module khác nhau, làm mất tất cả modes.
- `deep-has-private=true`, `private-call=PRIVATE_OK`: caller có `MODULE + PRIVATE` và `m.target` mở package cho `m.origin`, nên `privateLookupIn` hợp lệ.
- `deep-has-module=false`, `re-private-fails=true`: dù private lookup có thể gọi secret, nó **không còn `MODULE`** để gọi `privateLookupIn` nối tiếp.
- `public-prev-null=true`: public lookup với `UNCONDITIONAL` vẫn không lưu previous.

**Không dùng nguyên con số `lookupModes()` làm test portable cho mọi lookup ở mọi JDK**; hãy kiểm tra từng bit cần thiết bằng `&` với constant của Javadoc. Ngoại lệ có chủ đích trong bài là `third-modes=0`: phép teleport qua ba module khác nhau được Javadoc quy định phải mất toàn bộ access modes.

## 12. Một private lookup đã teleport không thể «đệ quy nâng cấp» sang module khác

Giả sử:

```text
M0: origin.app.Main
      |
      | privateLookupIn(Target, root)
      | cần requires M1 và opens package M1 to M0
      v
M1: target.api.Target
      |
      | deep.has(PRIVATE)  = true
      | deep.has(MODULE)   = false
      | deep.previous     = Main
      |
      +-- findStatic(Target.privateMethod)  -> được nếu đúng chữ ký
      |
      +-- privateLookupIn(OtherClass, deep) -> không đủ MODULE
```

Thậm chí nếu module đích tiếp theo có `opens` public, lookup `deep` vẫn không đáp ứng tiền điều kiện `MODULE + PRIVATE`. Đây là một giới hạn bảo vệ quyền xuyên module.

**Một sai lầm dễ gặp:** «Lookup có `PRIVATE` chắc chắn là full privilege». Không đúng: full privilege cho `privateLookupIn` đòi cả `PRIVATE` **và** `MODULE`; lookup đã teleport có thể giữ `PRIVATE` nhưng không còn `MODULE`.

### 12.1. Khi target cùng module

Nếu caller lookup được tạo trong một module và `Target` ở **cùng module**, `privateLookupIn(Target, caller)` có thể trả lookup full privilege trên `Target` và previous `null`. Không có bước crossing module, nên không gắn «previous class ở module khác».

Điều này khác với `Lookup.in(Target.class)` trong cùng module: `in` chỉ **hạn chế hoặc giữ** quyền hiện có, không phải API đảm bảo tự tăng thành private access của class mới. Nếu code cần quyền private và hợp đồng cho phép, dùng `privateLookupIn` với đúng điều kiện.

## 13. Mở package bằng `exports` và `opens` phải có chủ đích

Đối với named modules, đừng gộp hai điều kiện sau:

| Khai báo | Ý nghĩa |
| --- | --- |
| `exports p;` | Public types trong package `p` accessible cho các modules đọc module đó. |
| `exports p to m.origin;` | Public types trong `p` accessible tới module `m.origin` trong phạm vi qualified export. |
| `opens p;` | Cho phép deep reflection vào `p` từ các modules khác theo hợp đồng JPMS. |
| `opens p to m.origin;` | Cho phép deep reflection vào `p` từ module `m.origin` cụ thể. |
| `requires m.target;` | Module hiện tại đọc `m.target`. |

Để tạo **private lookup xuyên module** với `privateLookupIn`, chỉ một `exports` **không đủ**. Cần `opens` thích hợp, caller có `PRIVATE+MODULE` và readability.

**Security:** Một package mở cho framework module cho phép framework thực hiện nhiều hành vi phản chiếu sâu hơn truy cập public API. Chỉ mở những package cần thiết và tới module tin cậy; tránh `opens` vô điều kiện nếu không cần.

### 13.1. `Class.forName` và `Lookup.in` không tương đương

`Class.forName("p.Target")` tìm và có thể khởi tạo một class theo tên, nhưng không tự tạo lookup với quyền private. Ngược lại `lookup.in(Target.class)` tạo một lookup mới với context và modes được giới hạn.

Với method handles, việc class **tồn tại và load được** không đồng nghĩa lookup có quyền tạo handle tới private method. Nếu class không thuộc package public/exported cho lookup, `Lookup.in(Target.class)` có thể tạo lookup **không còn mode nào**; không phải phương thức nâng quyền.

## 14. Phân biệt `previousLookupClass` với class loader và JPMS layer

Một `Class<?>` có thể thuộc **named module**, **unnamed module** hoặc module trong **custom ModuleLayer**. `previousLookupClass()` trả chính **Class object**, nên bạn có thể điều tra:

```java
Class<?> previous = lookup.previousLookupClass();
if (previous != null) {
    Module module = previous.getModule();
    System.out.println("previous-class=" + previous.getName());
    System.out.println("previous-module=" + module.getName());
}
```

Đây là đoạn minh họa trong phương thức có `lookup`. Với **unnamed module**, `module.getName()` có thể là `null`. Không coi `null` ở tên module là lỗi: nó khác `previousLookupClass()==null`.

- `Class.getClassLoader()` cho biết loader của class; **không phải** previous lookup class.
- `Class.getModule()` cho biết module class thuộc về; **không phải** bit mask quyền.
- `Class.getModule().getLayer()` có thể giúp nhận diện layer, nhưng module của một số class có thể không thuộc một `ModuleLayer` quản lý theo cách bạn giả định.
- `previousLookupClass` không lưu mọi hop đã qua, không phải stack trace và không cho biết thread nào tạo lookup.

Một lớp `T` nằm trong custom ModuleLayer chỉ accessible nếu có module graph và loader phù hợp; `Lookup.in(T.class)` không tự thêm `requires` vào module graph hoặc tải module chưa resolve. Việc tạo module layer là quy trình riêng với `ModuleFinder`/`Configuration`/`ModuleLayer`.

## 15. Cách kiểm tra lookup trong code thực tế

Có thể tạo một helper chỉ để **quan sát metadata**, không log toàn bộ thông tin riêng tư:

```java
static void describe(String label, MethodHandles.Lookup lookup) {
    Class<?> current = lookup.lookupClass();
    Class<?> previous = lookup.previousLookupClass();
    int modes = lookup.lookupModes();

    System.out.println(label + ".lookupClass=" + current.getName());
    System.out.println(label + ".previousLookupClass="
            + (previous == null ? "<none>" : previous.getName()));
    System.out.println(label + ".MODULE="
            + ((modes & MethodHandles.Lookup.MODULE) != 0));
    System.out.println(label + ".PRIVATE="
            + ((modes & MethodHandles.Lookup.PRIVATE) != 0));
    System.out.println(label + ".PUBLIC="
            + ((modes & MethodHandles.Lookup.PUBLIC) != 0));
}
```

Đây là **method minh họa** để thêm vào class đã `import java.lang.invoke.MethodHandles;`. Nó giúp phân tích ba trạng thái:

1. Lookup có đứng ở class bạn nghĩ không?
2. Nó vừa teleport từ class/module nào?
3. Nó còn những mode nào, nhất là `MODULE` và `PRIVATE`?

**Không dùng `Lookup.toString()` như một định dạng log có contract bất biến giữa các phiên bản**. Javadoc có mô tả cách hiển thị, nhưng khi test quyền nên so sánh `lookupClass()`, `previousLookupClass()` và các bits của `lookupModes()` thay vì parse chuỗi `toString()`.

### 15.1. Kiểm thử failure path

Thay vì bắt mọi exception rồi cho là thành công, hãy bắt loại lỗi bạn chờ và xác nhận:

```java
boolean denied = false;
try {
    MethodHandles.privateLookupIn(Third.class, deep);
} catch (IllegalAccessException expected) {
    denied = true;
}
if (!denied) {
    throw new AssertionError("Expected private access to be denied");
}
```

Mẫu này nằm trong `Main` của ví dụ ba module. `deep` là lookup đã teleport sang M1 mà không còn `MODULE`; do đó `privateLookupIn` không thể cấp quyền mới. Một test tốt phải kiểm chứng **quyền được cấp** và **quyền bị từ chối**.

### 15.2. Nếu `previousLookupClass()==null` thì kết luận gì?

**Chỉ kết luận:** Lookup hiện tại **không có previous lookup class được ghi nhận** theo hợp đồng. Nó có thể:

- Được tạo trực tiếp bằng `MethodHandles.lookup()`;
- Là `publicLookup()` hoặc lookup có `UNCONDITIONAL`;
- Được chuyển trong cùng module từ một lookup có previous null;
- Là lookup được tạo bởi `privateLookupIn` trong cùng module.

Không được suy ra «lookup chắc chắn có full privilege» hay «chưa từng có thao tác tạo/cấu hình nào» chỉ từ việc previous bằng null. Muốn đánh giá quyền, phải kiểm tra modes và JPMS graph.

## 16. Lỗi thường gặp và cách xử lý

| Hiểu nhầm/lỗi | Lý do | Cách sửa |
| --- | --- | --- |
| «`previousLookupClass` luôn là caller gốc đầu tiên». | Nó cập nhật theo lookup class ngay trước lần đổi module; không lưu full history. | Theo dõi từng hop qua `lookupClass`/`previousLookupClass`. |
| «Đổi class trong cùng module cũng luôn cập nhật previous». | Same-module `in` **giữ** previous cũ. | Dùng quy tắc same-module vs cross-module. |
| «Có previous thì có quyền private của previous class». | Previous chỉ ràng buộc public cross-module checks; không chuyển private capability. | Xem `lookupModes` và accessibility. |
| «`Lookup.in` sang M1 cho toàn bộ quyền như gọi `lookup()` tại M1». | `in` không tăng quyền, mất MODULE qua module. | Chỉ xin quyền hợp lệ bằng `privateLookupIn`. |
| «`PRIVATE` một mình cho phép `privateLookupIn`». | API yêu cầu cả `PRIVATE` và `MODULE`. | Kiểm tra hai bit và module readability/opens. |
| «`exports` đủ cho private method». | Exports hỗ trợ public API, deep reflection cần opens. | Dùng qualified `opens p to m.origin` khi có nhu cầu hợp lệ. |
| «Lookup teleport sang module thứ ba vẫn còn PUBLIC như cũ». | Ba module khác nhau trong `in` làm mất toàn bộ quyền. | Dùng lookup trước để tra public member có thể truy cập, không teleport không cần thiết. |
| «Không thể find public method ở M2 nếu lookup đã M0→M1». | Hai-module `PUBLIC` có thể truy cập M2 nếu **cả M0 và M1 đều đọc M2** và package export phù hợp. | Phân biệt `findStatic(M2Class)` với `in(M2Class)`. |
| «`publicLookup` cũng phải ghi previous khi chuyển». | `UNCONDITIONAL` là ngoại lệ; previous null. | Kiểm tra mode `UNCONDITIONAL`. |
| «`previousLookupClass()==null` nghĩa là lookup full privilege». | Null không xác định các modes. | Luôn dùng `lookupModes()` và JPMS graph. |
| «`Class.forName` đã load class nên private lookup chắc chắn được». | Load class khác kiểm tra quyền method handle. | Kiểm tra `reads`, `opens`, `PRIVATE`, `MODULE`. |
| «`privateLookupIn` lỗi thì bắt `InaccessibleObjectException`». | Method này khai báo `IllegalAccessException` cho lỗi access. | Bắt/kiểm tra đúng exception theo Javadoc. |
| «Dùng `dropLookupMode` rồi `in` để khôi phục quyền». | Lookup modes không tự tăng trở lại. | Chỉ nguồn lookup có quyền phù hợp mới cấp năng lực mới. |
| «Chia sẻ một full-privilege lookup cho plugin là vô hại». | Lookup là capability, có thể tạo handles tới private members. | Trao lookup quyền tối thiểu, cân nhắc `publicLookup` hoặc drop modes. |
| «Handle đã tạo sẽ bị thu hồi khi tạo lookup yếu hơn». | Tạo lookup mới không tự thu hồi quyền của method handle cũ. | Kiểm soát khi tạo/chia sẻ handles và quyền ngay từ đầu. |

## 17. An toàn khi xây thư viện và framework

### 17.1. Lookup là một capability cần bảo vệ

Một `MethodHandles.Lookup` được tạo tại class có quyền cao có thể tạo handles truy cập thành viên vốn không public. Truyền lookup ấy cho code bên ngoài module có thể trao quyền mạnh hơn bạn dự kiến.

**Khuyến nghị:**

1. Không đưa full-privilege lookup vào public API nếu chỉ cần lookup public.
2. Khi chỉ cần public exported members, thử `MethodHandles.publicLookup()`.
3. Nếu cần truy cập nội bộ, chỉ cung cấp method handles đã được tạo cho những phương thức cụ thể thay vì trao cả lookup có thể tìm thành viên khác.
4. Dùng `Lookup.dropLookupMode(int)` khi cần giới hạn lookup trước khi chia sẻ, nhưng hiểu việc drop một mode có thể làm mất thêm các modes phụ thuộc; kiểm tra `lookupModes` sau đó.
5. Dùng qualified `opens` cho module framework thực sự tin cậy, không mở mọi package vô điều kiện.
6. Giữ module boundaries và test quyền bị từ chối, không chỉ kiểm tra đường thành công.

**Một caveat:** `MethodHandles.publicLookup()` với `UNCONDITIONAL` có chính sách public access riêng. Nếu framework cần ràng buộc nghiêm ngặt «cả origin và target đều reads module kia», đừng thay thế mọi lookup bằng publicLookup mà không xem điều kiện bảo mật.

### 17.2. Làm sao chia sẻ method handle an toàn?

Với một handle đã tạo:

```java
MethodHandle handle = lookup.findStatic(
        Service.class, "run", MethodType.methodType(void.class));
```

Đây là **snippet minh họa**, `Service` phải tồn tại và method public/accessible theo lookup. Sau khi handle được tạo, Java không kiểm tra lại quyền theo caller của mỗi `handle.invokeExact()` như core reflection đối với từng lần gọi. Vì thế **trao một handle** cũng là trao năng lực gọi method đó; kiểm tra chính sách chia sẻ.

### 17.3. Không dùng `--add-opens` bừa bãi để «sửa cho chạy»

Nếu gặp `IllegalAccessException` từ `privateLookupIn`, cần xác định:

- Có `requires` hoặc readability tương đương chưa?
- Package target có `opens` cho caller module chưa?
- Lookup caller có cả `PRIVATE` và `MODULE` không?
- Target có phải class hợp lệ không?
- Lookup đã teleport qua module khác trước đó làm mất `MODULE` chưa?

Bổ sung `--add-opens module/package=some.module` từ launcher có thể hữu ích trong môi trường cần cấu hình linh hoạt, nhưng **không** khôi phục `MODULE` bit đã mất trong lookup hiện tại. Nếu quyền thiếu vì teleport, phải xem lại **nơi tạo lookup ban đầu** và đường đi của nó, không dùng flag như một cách tự nâng quyền không kiểm soát.

## 18. Checklist chẩn đoán khi lookup thất bại

1. **Ghi nhận lớp:** `lookup.lookupClass().getName()`.
2. **Ghi nhận previous:** `lookup.previousLookupClass()` có `null` không? Nếu không, lấy class/module.
3. **Kiểm tra modes:** `PUBLIC`, `PRIVATE`, `MODULE`, `UNCONDITIONAL`; không đoán từ tên biến.
4. **Kiểm tra module graph:** Module nguồn có đọc module đích? `exports` có đúng scope?
5. **Kiểm tra `opens`:** Nếu deep reflection, package đích có mở cho module caller không?
6. **Kiểm tra số lần teleport:** Có vừa đi M0→M1 rồi M1→M2, làm modes bằng `0`?
7. **Kiểm tra loại thao tác:** Bạn thực sự cần `in(T.class)` hay chỉ `findStatic/findVirtual` trên lookup hiện tại?
8. **Kiểm tra chữ ký method:** `MethodType` có đúng return/argument types? Tránh nhầm lỗi `NoSuchMethodException` với lỗi access.
9. **Kiểm tra module path/runtime image:** Class target có được resolve vào layer và accessible theo classloader không?
10. **Kiểm tra failure code:** Bắt `IllegalAccessException` từ lookup, không che nguyên nhân bằng `catch (Exception)` trống.
11. **Kiểm tra security:** Có vô tình truyền full lookup hoặc opens quá rộng cho plugin?
12. **Kiểm tra test:** Tạo test success/failure với modules thật, không chỉ chạy trong unnamed module của IDE.

### 18.1. Khác biệt lỗi thường gặp

| Lỗi | Nguyên nhân điển hình |
| --- | --- |
| `IllegalAccessException` khi `Lookup.findStatic` | Class/member không accessible bởi lookup hoặc modes đã bị giảm. |
| `NoSuchMethodException` | Tên, loại static/virtual hoặc `MethodType` không đúng; đừng vội cho là do module. |
| `IllegalAccessException` từ `privateLookupIn` | Thiếu `PRIVATE/MODULE`, readability hoặc opens, hoặc quyền không thỏa. |
| `IllegalArgumentException` từ `Lookup.in` | Target là primitive, void hoặc array class theo Javadoc. |
| `NullPointerException` từ `Lookup.in` | Tham số target class là `null`. |
| `WrongMethodTypeException` khi gọi handle | Kiểu invocation không khớp chữ ký handle; đây là giai đoạn **gọi**, không phải tạo quyền. |
| `ClassNotFoundException` khi `Lookup.findClass` | Class không được classloader của lookup tìm thấy, hoặc target cần module chưa available. |
| `LinkageError` | Vấn đề linkage/binary compatibility hoặc phụ thuộc lúc link/classload. |

## 19. Bài tập và đáp án

### Bài 1 — Tạo lookup mới

```java
Lookup l = MethodHandles.lookup();
System.out.println(l.previousLookupClass() == null);
```

**Đáp án:** `true`. Lookup gốc tạo bởi `MethodHandles.lookup()` không có previous lookup class.

### Bài 2 — Hai class cùng module

`C` và `D` ở module M0. `l = MethodHandles.lookup()` tạo tại C, sau đó `l2 = l.in(D.class)`. `l2.previousLookupClass()` là gì?

**Đáp án:** `null`. `in` trong cùng module giữ previous cũ; lookup gốc previous null.

### Bài 3 — Teleport sang module thứ hai

`C∈M0`, `D∈M1`; `l` tạo ở C và D accessible. `l2 = l.in(D.class)`. Hai thuộc tính quan trọng?

**Đáp án:** `l2.lookupClass() == D.class` và `l2.previousLookupClass() == C.class`. `MODULE` bị mất; quyền public có thể còn tùy access checks.

### Bài 4 — Đổi class trong module thứ hai

`l2` từ bài 3 chuyển sang `D2` cùng M1. Previous thành `D.class` hay vẫn `C.class`?

**Đáp án:** Vẫn `C.class`, bởi không đổi module trong bước D→D2.

### Bài 5 — Tới module thứ ba

`l3 = l2.in(E.class)`, `E∈M2` khác M0/M1. Previous của l3 là gì? Modes thế nào?

**Đáp án:** `l3.previousLookupClass() == D.class`; `l3.lookupModes()==0` theo quy tắc 3-module teleport. Previous không biến mất chỉ vì quyền đã về 0.

### Bài 6 — Public lookup

`MethodHandles.publicLookup().in(D.class).previousLookupClass()` có phải D không?

**Đáp án:** Không. Với lookup còn `UNCONDITIONAL`, previous là `null`.

### Bài 7 — PRIVATE nhưng không MODULE

Một `Lookup` có `PRIVATE` nhưng không có `MODULE`. Gọi `privateLookupIn(T.class, lookup)` được không?

**Đáp án:** Không. API yêu cầu **cả hai** modes. Khi thiếu `MODULE`, không thể cấp một private lookup mới bằng cách này.

### Bài 8 — Exports và opens

Module M1 `exports target.api` nhưng không `opens target.api to M0`. Caller lookup ở M0 có `PRIVATE + MODULE` và M0 reads M1. Có chắc `privateLookupIn(Target.class, caller)` thành công không?

**Đáp án:** Không. Cross-module deep reflection cần package **opens** cho caller module, không chỉ exports.

### Bài 9 — Find public ở module thứ ba

`l2` ở M1 có previous ở M0. Cả M0/M1 reads M2, class E public ở package M2 exports cho cả hai. `l2.findStatic(E.class,...)` có thể thành công không? Còn `l2.in(E.class)`?

**Đáp án:** Find public method có thể thành công nếu member/signature accessible. `in(E.class)` là lần teleport mới sang module thứ ba, khiến modes thành 0.

### Bài 10 — Chuyển lại module cũ

Từ M0→M1, sau đó `lookup.in(C2.class)` với C2 ở M0. Có khôi phục full privilege ban đầu không?

**Đáp án:** Không. Lookup đã mất quyền khi teleport không thể tự nâng quyền lại nhờ `in`. Previous giờ ghi lookup class cũ ở M1; một phần public access có thể còn nếu các điều kiện phù hợp.

### Bài 11 — So sánh với call stack

`previousLookupClass()` có phải class gọi method hiện tại hoặc stack frame trước không?

**Đáp án:** Không. Nó là metadata của `Lookup` về lần teleport qua module, không phải runtime call stack.

### Bài 12 — Method handle đã được tạo

Nếu bạn tạo handle private bằng lookup hợp lệ, rồi tạo lookup yếu hơn bằng `dropLookupMode`, handle cũ có tự mất khả năng gọi private method không?

**Đáp án:** Không có cơ chế «thu hồi» handle như vậy. Handle đã tạo là capability được kiểm tra lúc lookup/creation; chính sách chia sẻ handle phải được kiểm soát riêng.

## 20. Nguồn chính thức còn áp dụng

1. [Java SE 25 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): phần **Cross-module lookups**, `lookupClass()`, `previousLookupClass()`, `lookupModes()`, `in(Class<?>)` và kiểm tra quyền truy cập.
2. [Java SE 17 — `MethodHandles.Lookup.previousLookupClass()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#previousLookupClass()): ghi nhận previous lookup class ở module khác hoặc `null`, API **Since 14**.
3. [Java SE 25 — `MethodHandles.privateLookupIn`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup)): điều kiện `PRIVATE + MODULE`, readability/opens, previous và mất MODULE khi cross-module.
4. [Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): API tương thích với các lệnh `--release 17` trong ví dụ.
5. [Java Language Specification SE 25 — `7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.7): `requires`, `exports`, `opens` và cấu trúc module descriptors.
6. [Java Platform Module System — `Module` API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Module.html): `canRead`, `isExported`, `isOpen` để chẩn đoán module graph.
7. [Java SE 25 — `MethodHandle`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact()` và đặc tính gọi method handle sau khi lookup kiểm tra quyền.
8. [Java SE 25 — `MethodType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodType.html): chữ ký method khi gọi `findStatic` và `findVirtual`.
9. [Java SE 25 — `Lookup.dropLookupMode`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#dropLookupMode(int)): hạn chế quyền lookup, không làm tăng quyền.
10. [Java SE 25 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): module layer, boot layer và module graphs cho runtime/plugin systems.

**Tóm tắt cuối:** `previousLookupClass()` thường **`null` ở lookup gốc**, **giữ nguyên khi `in` đổi lớp trong cùng module**, và **ghi lại lookup class cũ khi chuyển sang module khác**. Chuyển module qua `Lookup.in` loại `MODULE`; tới module thứ ba khi có previous ở module khác sẽ mất mọi modes. `privateLookupIn` cho phép private access xuyên module **chỉ khi** caller có `PRIVATE+MODULE`, đọc được target module và package target được mở phù hợp; kết quả cũng không còn `MODULE`. Trong mọi trường hợp, **kiểm tra `lookupModes`, module readability và exports/opens**, không dùng `previousLookupClass` như một phép đo quyền duy nhất.