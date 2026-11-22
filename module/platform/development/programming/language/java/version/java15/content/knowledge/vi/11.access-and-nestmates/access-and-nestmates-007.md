# Giới hạn chia sẻ lookup có đặc quyền trong Java

Trong Java, `java.lang.invoke.MethodHandles.Lookup` là **đối tượng mang quyền** (*capability object*): nó quyết định một đoạn mã có thể tạo `MethodHandle`, `VarHandle` hoặc định nghĩa lớp với những quyền truy cập nào. Một `Lookup` lấy từ `MethodHandles.lookup()` bên trong mã đáng tin cậy có thể mang quyền truy cập vào **thành viên `private`, quan hệ nestmate, package và module** của lớp tạo nó. Nếu đưa nguyên đối tượng ấy cho plugin, callback hoặc framework không có cùng mức tin cậy, bên nhận có thể sử dụng **quyền của lớp đã tạo lookup**, không chỉ quyền của chính nó.

Chủ đề này đặc biệt quan trọng với **Java 15 và các phiên bản Java hiện đại**, khi `Lookup.defineHiddenClass(...)` (Java 15) cho phép định nghĩa lớp ẩn, có tùy chọn `NESTMATE`. Nguyên tắc an toàn là **chỉ chuyển giao đúng quyền cần thiết**: ưu tiên interface, API kiểm soát hoặc một `MethodHandle` dành cho thao tác cụ thể; chỉ chia sẻ `Lookup` có đặc quyền với mã thật sự được tin tưởng.

## 1. Lookup là một quyền truy cập, không đơn thuần là tiện ích tìm method

Ví dụ trong một class đáng tin cậy:

```java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup ownerLookup = MethodHandles.lookup();
```

Lời gọi `MethodHandles.lookup()` là **caller-sensitive**: JVM xác định lớp gọi thực sự, rồi tạo đối tượng `Lookup` mang ngữ cảnh quyền của lớp ấy. Đối tượng giữ một **lookup class** và các **lookup modes**, chứ không tự đổi quyền mỗi khi được truyền cho một người gọi khác.

Qua `Lookup`, mã có thể yêu cầu:

- `findStatic(...)`, `findVirtual(...)`, `findConstructor(...)`, `findGetter(...)`, `findSetter(...)`: tạo method/field handle với kiểm tra quyền.
- `unreflect(...)` và các biến thể: chuyển một đối tượng reflection thích hợp thành handle, vẫn phải qua quy tắc quyền áp dụng.
- `defineClass(byte[])`: định nghĩa class có tên trong package phù hợp nếu lookup có quyền yêu cầu.
- `defineHiddenClass(byte[], boolean, ...)`: định nghĩa hidden class khi lookup có **full privilege access** và bytecode đáp ứng điều kiện.
- `privateLookupIn(Target.class, callerLookup)`: API tĩnh của `MethodHandles` để yêu cầu một lookup khác có thể truy cập private của `Target`, với kiểm tra điều kiện về quyền và module.

**Kiểm tra truy cập của method handle được thực hiện khi tạo handle**, không phải mỗi lần gọi `invokeExact(...)`. Vì vậy, một `MethodHandle` đã tạo để gọi phương thức riêng tư cũng là một capability. Đưa handle ấy cho bên khác là cố ý trao **quyền gọi đúng phương thức đó**; đưa cả `Lookup` có thể trao quyền **tự tìm nhiều phương thức/field khác**.

## 2. Các mức quyền và cách kiểm tra

Một `Lookup` mang tập các bit quyền (*lookup modes*) có thể xem qua `lookupModes()`. Trong JDK hiện đại có các mode như:

| Mode | Phạm vi ý nghĩa |
| --- | --- |
| `PUBLIC` | Quyền truy cập các thành viên public theo ngữ cảnh lookup và module |
| `PACKAGE` | Quyền truy cập cấp package nơi lookup hợp lệ |
| `PRIVATE` | Quyền truy cập private phù hợp lớp/nest và các quy tắc truy cập |
| `PROTECTED` | Quyền truy cập protected theo quy tắc JVM, có ràng buộc receiver/subclass |
| `MODULE` | Quyền có ngữ cảnh module của lookup class khi thực hiện một số kiểm tra module |
| `UNCONDITIONAL` | Mode đặc trưng của `publicLookup()`, dùng cho quyền public ở các package được export vô điều kiện |
| `ORIGINAL` | Đánh dấu lookup trực tiếp từ lời gọi `MethodHandles.lookup()` trong các JDK hiện đại; liên quan một số API caller-sensitive |

Các mode không phải là một “mật khẩu” để tự cộng/trừ tùy ý. Quyền truy cập còn phụ thuộc **lookup class, quan hệ nest, class loader, module, `exports`/`opens` và target member**.

Hai API kiểm tra rất hữu ích:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
boolean full = lookup.hasFullPrivilegeAccess();
int modes = lookup.lookupModes();
```

`hasFullPrivilegeAccess()` kiểm tra việc lookup có cả **`PRIVATE` và `MODULE`**. Kết quả `true` không có nghĩa là lookup có quyền vượt qua mọi module hay truy cập mọi private member của toàn JVM. Nó chỉ nói lookup có đặc quyền đầy đủ **theo ngữ cảnh lớp tạo nó**, và các API vẫn thực thi kiểm tra khác.

Không nên viết logic bảo mật dựa trên **một số nguyên mode mask cụ thể** vì quyền và cách biểu diễn có thể thay đổi giữa các bản JDK. Trong mã cần lựa chọn cách chia sẻ, hãy thiết kế capability hẹp trước, rồi sử dụng `hasFullPrivilegeAccess()` và `lookupModes()` để kiểm tra/chẩn đoán khi phù hợp.

## 3. Vì sao chia sẻ lookup gốc có thể nguy hiểm?

Giả sử một class chứa thông tin hoặc hành vi riêng tư:

```java
public class AccountCore {
    private static String internalToken() {
        return "private-value";
    }

    public static MethodHandles.Lookup privilegedLookup() {
        return MethodHandles.lookup(); // KHÔNG đưa bừa cho plugin.
    }
}
```

Đây là ví dụ **minh họa rủi ro**, chưa đầy đủ `import java.lang.invoke.MethodHandles;`. Nếu một bên khác được cung cấp lookup do `AccountCore` tạo, nó có thể thử dùng lookup đó để tìm thành viên private mà ngữ cảnh `AccountCore` có quyền truy cập. Đây là việc **ủy quyền** chứ không phải bypass bằng cách đổi tên class.

Nguy cơ tăng lên khi bên nhận có quyền:

- Tìm method/field ngoài những gì chức năng plugin thực sự cần.
- Tạo handle tới private constructor hoặc private method, rồi lưu handle để sử dụng về sau.
- Dùng khả năng định nghĩa class trong package khi có mode phù hợp, hoặc định nghĩa hidden class khi có full privilege.
- Truy cập một nest hoặc package có ranh giới nội bộ nhạy cảm khi lookup có quyền tương ứng.
- Chuyển tiếp `Lookup` hoặc handle nhận được sang một bên thứ ba.

**`private` không còn là lớp bảo vệ riêng biệt khi chính mã sở hữu đã tự trao capability có quyền truy cập vào nó.** Phần cần bảo vệ không chỉ là tên API mà còn là **vị trí lưu trữ, kênh truyền và phạm vi người nhận lookup**.

Không đặt lookup gốc vào trường `public static`, không lưu trong context/map mà plugin có thể đọc, không cho phép code không tin cậy yêu cầu tùy ý một `Lookup` đặc quyền. Nếu thật sự phải ủy quyền cho một code generator đáng tin cậy, cần ràng buộc rõ phạm vi package, module, mã bytecode và vòng đời của quyền ấy.

## 4. Quan hệ nestmate làm quyền riêng tư đáng chú ý hơn

Từ Java 11, JVM hỗ trợ **nest**: các class cùng một nest có thể truy cập private member của nhau theo quy tắc JVM. Một lớp ngoài và lớp lồng `private static` thường cùng một nest.

```java
public class Outer {
    private static class Inner {
        private static String secret() {
            return "private-value";
        }
    }
}
```

`MethodHandles.lookup()` trong `Outer` có thể tạo handle đến `Inner.secret()` vì **nestmate access**, miễn lời gọi lookup được thực hiện với quyền hợp lệ. Nhưng một lookup đã bị bỏ mode `PRIVATE` không còn quyền thực hiện truy cập private như vậy.

Với hidden class:

```java
MethodHandles.Lookup hiddenLookup = ownerLookup.defineHiddenClass(
        trustedClassBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
```

Đây là **mã minh họa**, giả định `ownerLookup` được lấy từ lớp đáng tin và `trustedClassBytes` là `byte[]` chứa class-file hợp lệ trong đúng package. `defineHiddenClass(...)` yêu cầu lookup có full privilege access, và `NESTMATE` có thể cho hidden class thuộc nest của lookup class. Điều này **không tự tạo sandbox**, cũng không cho phép định nghĩa lớp ở package bất kỳ.

Nếu đưa full-privilege lookup cho một bộ sinh bytecode không tin cậy, bạn không chỉ cho phép nó tạo “adapter” thông thường; bạn có thể cho nó khả năng tạo **mã JVM chạy với ngữ cảnh truy cập rất nhạy cảm**. Vì vậy cần giới hạn nguồn bytecode, mức tin cậy của framework và quyền lookup truyền vào.

## 5. Ví dụ Java 17+ hoàn chỉnh: lookup gốc, lookup giới hạn và publicLookup

Chương trình sau tạo một class lồng private trong cùng nest, dùng lookup chủ sở hữu để tạo handle cho một thao tác đã chọn, rồi thử quyền truy cập private với một lookup đã bị thu hẹp. Đây là ví dụ độc lập, **không cần thư viện ngoài hoặc JVM flag đặc biệt**.

Tạo file `LookupBoundaryDemo.java` theo UTF-8:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupBoundaryDemo {
    private static final class Vault {
        private static String secret() {
            return "private-value";
        }

        private static String greet(String name) {
            return "Hello, " + name;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup owner = MethodHandles.lookup();

        // Loại bỏ quyền PRIVATE; vẫn có thể còn các mode khác.
        MethodHandles.Lookup narrowed =
                owner.dropLookupMode(MethodHandles.Lookup.PRIVATE);

        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();

        System.out.println("ownerFull=" + owner.hasFullPrivilegeAccess());
        System.out.println("narrowedFull=" + narrowed.hasFullPrivilegeAccess());
        System.out.println("publicFull=" + publicOnly.hasFullPrivilegeAccess());

        // Chủ sở hữu chủ động tạo một handle chỉ tới greet().
        MethodHandle allowed = owner.findStatic(
                Vault.class, "greet",
                MethodType.methodType(String.class, String.class));

        String greeting = (String) allowed.invokeExact("Lan");
        System.out.println("selectedHandle=" + greeting);

        // Lookup đã mất PRIVATE không còn quyền này.
        try {
            narrowed.findStatic(
                    Vault.class, "secret",
                    MethodType.methodType(String.class));
            System.out.println("narrowedPrivate=allowed");
        } catch (IllegalAccessException e) {
            System.out.println("narrowedPrivate=denied");
        }

        // Không thể lấy lại private privilege từ lookup đã hạ quyền.
        try {
            MethodHandles.privateLookupIn(Vault.class, narrowed);
            System.out.println("upgrade=allowed");
        } catch (IllegalAccessException e) {
            System.out.println("upgrade=denied");
        }

        // Public lookup có thể dùng public API được truy cập hợp lệ.
        MethodHandle abs = publicOnly.findStatic(
                Math.class, "abs",
                MethodType.methodType(int.class, int.class));
        System.out.println("publicAbs=" + (int) abs.invokeExact(-7));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 LookupBoundaryDemo.java
java LookupBoundaryDemo
```

**Kết quả chính xác**, đã kiểm tra trên một JDK hiện đại:

```text
ownerFull=true
narrowedFull=false
publicFull=false
selectedHandle=Hello, Lan
narrowedPrivate=denied
upgrade=denied
publicAbs=7
```

### Phân tích từng kết quả

- `ownerFull=true`: `MethodHandles.lookup()` trực tiếp trong lớp `LookupBoundaryDemo` tạo lookup có quyền đầy đủ của lớp ấy.
- `narrowedFull=false`: bỏ `PRIVATE` khiến lookup không còn full privilege, dù nó có thể **vẫn giữ các quyền khác**. Không được hiểu việc bỏ riêng `PRIVATE` là đã tạo một `publicLookup()`.
- `publicFull=false`: `publicLookup()` không mang quyền riêng tư của lớp tạo chương trình; nó dùng để tìm API public đáp ứng điều kiện truy cập.
- `selectedHandle=Hello, Lan`: chính lớp có quyền đã chọn một method cụ thể và tạo handle tới nó. **Handle ấy vẫn có khả năng gọi `Vault.greet`**, dù phương thức là private. Vì thế không phát handle tới thao tác nhạy cảm cho code không đáng tin.
- `narrowedPrivate=denied`: quyền `PRIVATE` đã mất nên việc tìm `Vault.secret` bị từ chối.
- `upgrade=denied`: `MethodHandles.privateLookupIn(...)` không thể tạo quyền private mới khi caller lookup thiếu điều kiện full privilege.
- `publicAbs=7`: `publicLookup()` vẫn dùng được một public API thông thường `Math.abs`.

Chương trình này **không chia sẻ lookup gốc ra ngoài**. Nó giữ lookup có quyền trong mã đáng tin và minh họa việc tạo một handle đến đúng thao tác được chủ sở hữu lựa chọn. Trong sản phẩm, có thể xây một **interface hoặc API wrapper** để không cần đưa `MethodHandle` trực tiếp cho mã nghiệp vụ.

## 6. Các cách giảm quyền trước khi giao cho mã khác

| Cách | Dùng khi nào | Điểm cần cẩn trọng |
| --- | --- | --- |
| **Không giao lookup**; gọi qua interface/callback/service được kiểm soát | Phần lớn extension API, plugin, adapter | Thiết kế hành vi và kiểm tra input của API rõ ràng |
| Giao một **`MethodHandle` duy nhất** | Bên nhận chỉ cần gọi một operation đã chọn | Handle là capability gọi operation đó; không chuyển tiếp nhầm handle nhạy cảm |
| Dùng `MethodHandles.publicLookup()` | Chỉ cần tìm member public ở phạm vi API công khai phù hợp | Không tự động cho quyền truy cập vào mọi lớp ở mọi module |
| Dùng `lookup.dropLookupMode(mode)` | Muốn loại một nhóm quyền khỏi lookup hiện tại | Không nhất thiết trở thành “chỉ public”; cần kiểm tra **toàn bộ** quyền còn lại |
| Dùng `lookup.in(Target.class)` | Muốn chuyển ngữ cảnh lookup sang một lớp khác với giới hạn được JVM tính lại | Chuyển lookup class không tự nâng quyền và có thể làm mất quyền |
| Dùng `privateLookupIn(Target.class, callerLookup)` **với đối tác tin cậy** | Framework cần quyền truy cập private hợp lệ của target | Cần full privilege và điều kiện module; không phải phép biến lookup yếu thành mạnh |

### Vì sao không chỉ cần dropLookupMode(PRIVATE)?

`dropLookupMode(MethodHandles.Lookup.PRIVATE)` loại quyền private, nhưng lookup có thể **vẫn còn `PACKAGE`, `MODULE` hoặc khả năng truy cập những thành viên khác**. Nếu bên nhận không đáng tin và chỉ nên thao tác trên public API, `publicLookup()` hoặc việc **không giao lookup** thường tạo ranh giới dễ kiểm soát hơn.

`dropLookupMode` trả một đối tượng lookup **mới**; nó **không hạ quyền lookup gốc** và cũng không thu hồi method handles đã tạo trước đó. Những quyền đã được chuyển giao qua một handle vẫn tồn tại cùng handle khi nó có thể được gọi.

Ngoài ra, không có cơ chế phổ quát gọi “revocation” của `Lookup` để thu hồi tất cả các bản sao/handle mà bên khác đang giữ. Việc giới hạn quyền phải được thực hiện **trước khi cấp phát capability**.

### lookup.in(...) không phải đường tắt truy cập private

`lookup.in(Target.class)` tính lại ngữ cảnh lookup với các giới hạn phụ thuộc quan hệ giữa lớp cũ và lớp đích. Quyền chỉ có thể bị hạn chế thêm hoặc giữ mức hợp lệ, **không tự tăng lên**. Nó không thay thế `privateLookupIn` và không bỏ qua các điều kiện `exports`/`opens` của hệ thống module.

## 7. privateLookupIn và giới hạn của Java module

`MethodHandles.privateLookupIn(Target.class, callerLookup)` là cơ chế **có kiểm tra quyền**, không phải một phương thức “hack” để lấy private của bất kỳ class nào.

Tài liệu JDK mô tả điều kiện quan trọng:

1. `callerLookup` phải có **full privilege access**, tức có `PRIVATE` và `MODULE`.
2. `Target` phải là lớp hợp lệ (không phải primitive hoặc array).
3. Nếu lớp gọi và lớp đích ở **hai module khác nhau**, module của caller phải **read** module đích.
4. Module đích phải **opens** package chứa `Target` ít nhất cho module caller. Việc chỉ **exports** một package để truy cập public thông thường **không đồng nghĩa** với mở quyền deep reflection.
5. Với lookup trả về khi vượt ranh giới module, JDK giới hạn quyền; cụ thể lookup ấy **không còn `MODULE`**, ngăn việc dùng nó để tiếp tục “nhảy” đặc quyền tùy ý sang một module khác.

Nếu điều kiện không thỏa, API có thể ném `IllegalAccessException`. Không nên xử lý lỗi bằng cách mở toàn bộ module tùy tiện hoặc truyền lookup full-privilege ở phạm vi toàn ứng dụng.

Đối với một framework sinh mã chạy trong module riêng, hãy quyết định rõ **package nào cần mở, mở cho module nào và tại sao**. Ví dụ cấu hình module minh họa, **không phải khuyến nghị dùng nguyên xi**:

```java
module app.core {
    opens internal.model to trusted.generator;
}
```

Đoạn `module-info.java` này chỉ có ý nghĩa nếu thực tế có module tên `trusted.generator`, quan hệ module-read phù hợp và chương trình cần deep reflection tới `internal.model`. Khi mở package để một đối tác có thể tạo private lookup, cần coi đây là **sự ủy quyền truy cập sâu** và chỉ cấp cho code đáng tin.

## 8. Đặc biệt cẩn thận khi định nghĩa class hoặc hidden class

Hai API sau không chỉ “tìm phương thức”, mà có thể đưa **class mới** vào runtime:

```java
lookup.defineClass(classFileBytes);
lookup.defineHiddenClass(
        classFileBytes, true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
```

Đây là mã **minh họa**: `classFileBytes` phải là bytecode class-file hợp lệ trong đúng package, và lookup cần đủ quyền tương ứng. `defineHiddenClass(...)` đòi hỏi full privilege; `defineClass(...)` có yêu cầu riêng về package access. Khi dùng `NESTMATE`, hidden class có thể trở thành nestmate của lớp lookup theo quy tắc JVM và do đó thực hiện các truy cập private hợp lệ trong nest.

Một bộ sinh adapter đáng tin có thể cần quyền này. Tuy nhiên, **không giao lookup đặc quyền cùng khả năng quyết định bytecode tùy ý cho mã không đáng tin**. Hidden class không phải lớp cách ly bảo mật. Cần áp dụng nguyên tắc:

- Chủ sở hữu đáng tin quyết định **cấu trúc bytecode** sẽ được định nghĩa.
- Chỉ cấp lookup đủ quyền và đúng **runtime package/module** mà bộ sinh thực sự cần.
- Không dùng `NESTMATE` chỉ để vượt rào cản truy cập nội bộ; chỉ dùng khi hợp đồng triển khai cần và được cho phép.
- Giữ công cụ sinh bytecode, class-file parser và thư viện phụ thuộc được duy trì; kiểm tra input nếu chúng sinh mã theo dữ liệu ngoài.
- Nếu yêu cầu là **thực thi mã hoàn toàn không đáng tin**, cần một ranh giới cách ly thực sự ở cấp tiến trình/hệ điều hành hoặc dịch vụ; hidden class không đáp ứng mục tiêu ấy.

Trong trường hợp chỉ cần lambda hoặc một adapter đơn giản, hãy ưu tiên class/interface hoặc lambda thông thường thay vì tự dựng bytecode và xin một `Lookup` mạnh.

## 9. Thiết kế API chia sẻ an toàn trong plugin/framework

Ví dụ một extension chỉ cần chuẩn hóa nhãn:

```java
import java.util.Locale;
import java.util.function.UnaryOperator;

public final class LabelApi {
    private LabelApi() {}

    private static String normalize(String label) {
        return label.strip().toUpperCase(Locale.ROOT);
    }

    // API cấp cho extension: một hành vi cụ thể, không phải Lookup gốc.
    public static UnaryOperator<String> normalizer() {
        return LabelApi::normalize;
    }
}
```

Đoạn là một **class có thể biên dịch độc lập** nếu lưu trong `LabelApi.java`; ví dụ chỉ trình bày thiết kế API nên không có `main` và không công bố stdout cố định. Bên dùng nhận một `UnaryOperator<String>`, được quyền gọi đúng hành vi mà API cho phép, không có đối tượng `Lookup` để tìm tất cả các member khác.

Đối với dự án thật, cần thêm validation, giới hạn dữ liệu, chính sách thời gian chạy và quản lý tài nguyên tùy chức năng của extension. Việc trả callback đã lựa chọn không thay thế kiểm soát truy cập ở tầng nghiệp vụ.

**Checklist khi review quyền chia sẻ:**

1. Bên nhận **có bắt buộc cần `Lookup` không**, hay chỉ cần một interface, callback hoặc method handle đã chọn?
2. Ai tạo lookup, từ **class/module nào**, và bên nhận có độ tin cậy tương đương không?
3. Lookup còn các mode nào sau `dropLookupMode(...)`? Có vô tình giữ `PACKAGE`, `MODULE` hoặc quyền mở rộng không?
4. Bên nhận có thể **giữ lại hoặc chuyển tiếp** lookup/handle sau khi thao tác kết thúc không?
5. Module đã `opens` những package nào, cho module nào? Có đang mở rộng quá mức không?
6. Bên nhận có thể dùng lookup để `defineClass`/`defineHiddenClass` hoặc dùng bytecode không tin cậy không?
7. Nếu method handle chỉ được phép truy cập một operation, operation ấy có thực sự an toàn để giao cho bên nhận không?
8. Có bài kiểm thử **đường được phép** và **đường bị từ chối** như ví dụ ở mục 5 không?

## 10. Lỗi thường gặp

| Nhầm lẫn | Hệ quả/cách hiểu đúng |
| --- | --- |
| `MethodHandles.lookup()` trả một tiện ích vô hại để chia sẻ | Nó mang quyền theo **lớp gọi thực sự**, cần coi như capability |
| Bên nhận lookup chỉ có quyền của chính bên nhận | Lookup giữ ngữ cảnh quyền của **lookup class** đã được ghi khi tạo |
| Bỏ `PRIVATE` tức là chỉ còn public | Các mode `PACKAGE`/`MODULE` hoặc khác có thể vẫn còn |
| `hasFullPrivilegeAccess() == true` cho phép truy cập mọi private member trong JVM | Module, package, nest, lookup class và điều kiện target vẫn có hiệu lực |
| `lookup.in(Target.class)` có thể tự nâng quyền | Nó **không** khôi phục quyền đã mất |
| `privateLookupIn` có thể phục hồi `PRIVATE` từ một public lookup | Cần caller lookup có `PRIVATE` và `MODULE` cùng điều kiện module |
| Chỉ `exports` package là đủ cho private cross-module lookup | Thông thường cần **`opens`** package đích cho caller module |
| Tạo handle cho private method rồi trao ra ngoài thì không ai gọi được | Handle đã được kiểm tra tại **lúc tạo** và có thể được gọi theo capability ấy |
| Thu hẹp lookup gốc sẽ thu hồi những handle đã trao | `dropLookupMode` không thu hồi capability đã phát |
| Hidden class có `NESTMATE` tự tạo sandbox | Nó là cơ chế liên kết và truy cập JVM, không phải sandbox |
| Lỗi `IllegalAccessException` nên xử lý bằng cách `open module` toàn bộ | Cần giới hạn module/package theo thiết kế thay vì mở rộng vô điều kiện |

## 11. Bài tập tự kiểm tra

**Tình huống A.** Một plugin chỉ cần gọi `calculateTax(amount)`, nhưng mã chủ sở hữu định trả luôn lookup được tạo bằng `MethodHandles.lookup()` để plugin tự tìm method. Có rủi ro gì? Thiết kế nào phù hợp hơn?

**Tình huống B.** Sau khi gọi `owner.dropLookupMode(PRIVATE)`, một nhà phát triển truyền lookup kết quả cho đối tác và tuyên bố rằng nó giống hệt `publicLookup()`. Nhận định đúng không?

**Tình huống C.** Một bộ sinh mã bên ngoài module `app.core` muốn `privateLookupIn(Model.class, callerLookup)`. Chỉ thêm `exports internal.model` có đủ không?

**Tình huống D.** Một `MethodHandle` tới private method đã được tạo hợp lệ, sau đó chương trình hạ quyền một `Lookup` khác. Quyền gọi của method handle có tự động bị thu hồi không?

**Đáp án:**

1. Plugin có thể dùng lookup để tìm thêm các member ngoài `calculateTax` mà lookup class có quyền truy cập. Nên giao một interface hoặc handle **chỉ cho đúng thao tác**, sau khi xác định thao tác ấy an toàn cho plugin.
2. Không. `dropLookupMode(PRIVATE)` không bảo đảm xóa `PACKAGE`/`MODULE`. Muốn public-only, cân nhắc `MethodHandles.publicLookup()` hoặc không chia sẻ lookup.
3. Không. Với truy cập private qua module boundary, caller cần full privilege, module-read phù hợp và module đích **opens** package cho module caller. `exports` chỉ phục vụ phạm vi truy cập public thông thường.
4. Không. Kiểm tra quyền tạo handle xảy ra khi tạo; handle đã phát vẫn là một capability cho thao tác đã được cấp, miễn nó còn sử dụng được và không bị ràng buộc bởi điều kiện nghiệp vụ khác.

## Tài liệu tham khảo còn áp dụng

- [Oracle Java SE 25 — MethodHandles](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()` và `privateLookupIn(...)`.
- [Oracle Java SE 25 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): access checking, `lookupModes()`, `hasFullPrivilegeAccess()`, `dropLookupMode(...)`, `in(...)`, `defineClass` và `defineHiddenClass`.
- [Oracle Java SE 25 — MethodHandle](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/invoke/MethodHandle.html): quyền gọi và chữ ký của method handle.
- [OpenJDK — JEP 371: Hidden Classes](https://openjdk.org/jeps/371): mục tiêu và ranh giới sử dụng hidden class được giới thiệu ở Java 15.