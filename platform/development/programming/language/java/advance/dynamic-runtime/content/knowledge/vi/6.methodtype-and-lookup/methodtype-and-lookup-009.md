# 6.9. Thời điểm kiểm tra quyền và trách nhiệm khi chia sẻ `Lookup` hoặc method handle riêng tư

`java.lang.invoke.MethodHandles.Lookup` và `java.lang.invoke.MethodHandle` là hai kiểu đối tượng mang **quyền năng truy cập (capability)**, nhưng chúng trao quyền ở hai mức rất khác nhau:

- **`Lookup`** có thể được dùng để **tạo thêm** method handle/field handle/constructor handle cho những thành viên mà quyền của lookup đó cho phép.
- **`MethodHandle`** đã được tạo là một **khả năng gọi một đích cụ thể** theo `MethodType` xác định. Người nhận handle có thể gọi đích đó dù chính họ không đủ quyền để tạo handle tương tự.
- Với các factory như `Lookup.findStatic`, `findVirtual`, `findGetter`, **kiểm tra quyền truy cập diễn ra khi tạo handle**, dựa trên lookup class và quyền của `Lookup`. Khi dùng `invoke` hoặc `invokeExact` trên handle hợp lệ, Java **không kiểm tra lại quyền private/public theo class của từng người gọi**.
- Quyền của handle **không bao gồm miễn trừ kiểm tra kiểu, các kiểm tra nghiệp vụ bên trong đích, hay mọi kiểm tra bảo mật khác**. Handle vẫn có `MethodType`, việc gọi vẫn có thể ném exception, và code đích vẫn chạy như bình thường.

Vì vậy, khi chia sẻ một `Lookup` đầy quyền cho thành phần không tin cậy, bạn có thể vô tình cấp quyền **tìm thêm nhiều member riêng tư**. Khi chia sẻ một private method handle, bạn đang cho phép người nhận **gọi đúng đích được cấp** (kể cả gọi nhiều lần hoặc ở thời điểm không mong muốn). Cả hai đều là quyết định thiết kế ranh giới tin cậy, không đơn giản là truyền một đối tượng Java.

Bài này dùng Java 17+ và một thí nghiệm hai named modules để chứng minh từng luận điểm, sau đó đưa ra cách phân quyền và xử lý các rủi ro thường gặp.

## 1. `MethodHandles.lookup()` ghi nhận danh tính của ai?

Lời gọi:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

là **đoạn mã minh họa**, cần `import java.lang.invoke.MethodHandles;` trong một class thích hợp. `MethodHandles.lookup()` là phương thức **caller-sensitive**: kết quả gắn với **class thực sự gọi nó**, không phải class nào về sau giữ biến `lookup`.

Mỗi `Lookup` lưu ít nhất các khái niệm quan trọng:

| Thành phần | Ý nghĩa |
| --- | --- |
| `lookupClass()` | Class mà quyền truy cập của lookup được xác định theo |
| `lookupModes()` | Bit mask các mức quyền, ví dụ `PUBLIC`, `PACKAGE`, `PRIVATE`, `MODULE`, `PROTECTED`, `UNCONDITIONAL` |
| `previousLookupClass()` | Ngữ cảnh lookup class trước đó khi quyền lookup đã đi qua ranh giới module; thường `null` với `lookup()` trực tiếp |
| `hasFullPrivilegeAccess()` | Cho biết lookup có đủ đặc quyền theo hợp đồng API để thực hiện một số thao tác cần quyền cao |

`MethodHandles.lookup()` được tạo trong class của chính caller thường có full-privilege access đối với class đó. Điều này **không** có nghĩa nó tự có quyền vào mọi class khác: khi truy cập class/package/module khác, các quy tắc Java visibility, module readability, exports và opens vẫn được xem xét.

Quan trọng: một `Lookup` vẫn gắn với **quyền của lookup class đã được ghi nhận**, dù bạn chuyền tham chiếu `Lookup` tới object khác, thread khác, module khác hoặc lưu nó vào cache. Việc truyền đối tượng không tự biến lookup class thành class của người nhận.

### Hai thời điểm tách biệt

```text
Caller có quyền                         Consumer khác
      |                                     |
      | MethodHandles.lookup()              |
      v                                     |
  Lookup (ghi nhận caller)                  |
      |                                     |
      | findStatic / findVirtual / ...      |
      | -- KIỂM TRA QUYỀN Ở ĐÂY -->         |
      v                                     |
  MethodHandle được tạo thành công          |
      |                                     |
      + ------------ chuyển handle -------->|
                                            |
                                       invokeExact()
                                            |
                                   chạy target method
                           (KHÔNG xét lại access của
                            class Consumer khi gọi)
```

Nếu factory không đủ quyền, nó thường ném `IllegalAccessException` **trước khi** trả về handle. Nếu factory trả về handle, invocation sau đó chịu các quy tắc kiểu và hành vi thực thi, không yêu cầu người gọi từng có quyền direct access tới private member gốc.

## 2. Kiểm tra quyền ở lúc tạo handle, kiểm tra kiểu ở lúc invoke

Một lookup muốn tạo handle tới thành viên phải kiểm tra **nhiều chiều**:

1. Có tìm được class và member đúng tên/chữ ký/loại thao tác không?
2. Class và member đó có accessible đối với lookup class theo Java access rules không?
3. Lookup đang giữ các access modes nào? `PRIVATE`, `PACKAGE`, `MODULE`, ... có còn hợp lệ không?
4. Nếu qua JPMS module boundary, quan hệ `reads`, `exports` hoặc `opens` phù hợp có được thiết lập không? Một số chế độ lookup đặc biệt có quy tắc khác, chẳng hạn `publicLookup()` có `UNCONDITIONAL`.
5. Với API đặc biệt, có đủ điều kiện bổ sung hay không, chẳng hạn `privateLookupIn` đòi full-privilege lookup và openness thích hợp?

Các factory tiêu biểu: `findStatic`, `findVirtual`, `findSpecial`, `findConstructor`, `findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter`, và các biến thể `unreflect*`. Các biến thể có thể khác nhau về cách kiểm tra; đặc biệt, đừng tự động suy quy tắc của `unreflect` từ `findStatic`.

Ví dụ độc lập ở mục 5 sử dụng:

```java
MethodHandles.lookup().findStatic(
        VaultApi.class, "token", MethodType.methodType(String.class));
```

Đây là một **đoạn gọi nằm trong class `VaultApi` ở ví dụ chính**, không tự chạy riêng. Nó tìm phương thức **private static** `String token()` với `MethodType` không có tham số và có kiểu trả về `String`.

Sau khi tạo được `MethodHandle`, consumer gọi:

```java
String result = (String) handle.invokeExact();
```

đây cũng là **đoạn sử dụng biến `handle` có sẵn**. `invokeExact` đòi kiểu call site phù hợp chính xác với `MethodType` của handle. Việc ép kết quả về `String` trong biểu thức trên là một phần quan trọng của signature ở call site. Lỗi `WrongMethodTypeException` có thể xảy ra nếu khai báo call site sai, kể cả khi người gọi đã được cấp đúng handle.

**Không trộn lẫn hai câu hỏi:**

- **Có được tạo handle không?** → Quyết định theo access check của `Lookup` tại thời điểm tạo.
- **Gọi handle có thành công không?** → Phụ thuộc call-site method type, receiver/argument nếu có, target method, trạng thái runtime và các exception do target ném.

Một public wrapper chứa authorization check ở bên trong vẫn thực hiện check mỗi khi wrapper được gọi, dù handle trỏ tới wrapper đã được tạo trước đó. Handle chỉ bỏ việc kiểm tra lại **Java language access của chính handle**; nó không xóa logic nghiệp vụ của target.

## 3. So sánh với Core Reflection

`java.lang.reflect.Method` và `MethodHandle` có mô hình khác nhau:

| Điểm so sánh | Core Reflection (`Method`) | Method Handle |
| --- | --- | --- |
| Lấy đối tượng đại diện | `getMethod`, `getDeclaredMethod`, ... | `Lookup.find*`, `Lookup.unreflect*`, ... |
| Thời điểm kiểm tra access thông thường | `Method.invoke` kiểm tra theo caller khi gọi, nếu chưa suppress access checks | Kiểm tra lúc tạo handle bằng lookup context |
| Cách cấp deep access | `setAccessible`/`trySetAccessible` khi JPMS và quy tắc truy cập cho phép | `privateLookupIn` hoặc lookup có quyền phù hợp |
| Khi chuyển đối tượng tới caller khác | Caller của `Method.invoke` vẫn bị kiểm tra nếu chưa suppress; nếu accessible flag đã được bật hợp lệ thì đối tượng phản chiếu cũng có thể mang quyền truy cập sâu | Handle đã được tạo có thể được invoke bởi người nhận dù họ không thể tự tìm member gốc |
| Kiểu lời gọi | Thường qua `Object`/boxing và lỗi khi invoke | `MethodType`, `invokeExact` hoặc `invoke` với adaptation |
| Mức độ quyền khi chia sẻ | Tùy reflected object và accessible flag | Chính handle được cấp hoặc toàn bộ quyền mint handle của `Lookup` |

`Method.invoke` không phải không thể tạo capability: một `Method` có accessible flag đã được bật hợp lệ cũng cần được chia sẻ thận trọng. Bài học này chỉ nhấn mạnh **sự khác nhau về vị trí access check** và phạm vi quyền khi trao `Lookup`/handle.

Khi code đã có một `Method` và gọi `lookup.unreflect(method)`, hãy nhớ các quy tắc riêng: accessible flag có thể ảnh hưởng cách `unreflect` thực hiện access checks. Với bài kiểm tra trực tiếp thời điểm cấp quyền, nên dùng `findStatic`/`findVirtual` để giảm nhập nhằng.

## 4. Vì sao `Lookup` và private handle đều là capability nguy hiểm nếu phát tán bừa bãi?

### 4.1. Trao nguyên `Lookup` tương đương trao một công cụ tạo thêm quyền

Giả sử một class có hai private methods:

```java
private static String token() { return "TOKEN-42"; }
private static String internal() { return "INTERNAL"; }
```

Đây chỉ là **hai khai báo ví dụ trong `VaultApi`**, không phải cả một chương trình độc lập.

Nếu class đó trả `MethodHandles.lookup()` cho client, client nhận một đối tượng lookup mà **lookup class vẫn là class có quyền private**. Client có thể dùng nó để tìm `token`, `internal`, và những member khác nằm trong phạm vi quyền của lookup. Quyền của lookup không bị hạ xuống chỉ vì nó đi qua public method hoặc module boundary dưới dạng giá trị trả về.

Một full-privilege lookup còn có thể được dùng cho các API mang quyền lớn hơn truy cập private method, tùy điều kiện như `defineClass`, `defineHiddenClass`, `findSpecial`, ... Không nên xuất một đối tượng như vậy khỏi ranh giới tin cậy chỉ để cho bên ngoài gọi một method cụ thể.

### 4.2. Trao một `MethodHandle` thu hẹp phạm vi nhưng vẫn trao quyền thực thi

Một handle trỏ tới `token()` chỉ gọi đích đó, không tự cung cấp API tìm `internal()`. Tuy nhiên, nếu target làm thay đổi dữ liệu, đọc bí mật, thao tác tài nguyên hoặc gửi request, người cầm handle có thể gây **chính những tác dụng phụ ấy**.

Hãy coi handle như một **vé gọi hàm**, không phải dữ liệu metadata vô hại. Người nhận có thể:

- Gọi lại nhiều lần, lưu vào cache hoặc truyền tiếp cho nơi khác.
- Thay đổi thời điểm và tần suất gọi nếu bạn không có kiểm tra runtime bổ sung.
- Dùng các combinator/adaptation được API cho phép để bọc hoặc biến đổi một handle được cấp, nhưng không vì thế tự tìm được một private method khác.
- Nhận dữ liệu và exception mà target cho phép thoát ra, dù target vốn là private.

**Mức quyền được cấp luôn phải được đánh giá dựa trên tác dụng của target**, không chỉ modifier `private` hay số lượng handles.

### 4.3. Không có cơ chế thu hồi tự động

`Lookup.dropLookupMode(...)` tạo một **Lookup mới** đã giảm quyền. Nó **không sửa Lookup gốc**, không thu hồi MethodHandle đã cấp và không làm các references đang được giữ nơi khác tự mất quyền.

Ngay cả sau khi factory ngừng cấp handle mới, những private handles đã phát hành vẫn có thể được người nhận sử dụng. Nếu ứng dụng cần thu hồi quyền theo tài khoản, thời gian hoặc phiên, phải thiết kế một tầng kiểm tra trạng thái **trong đường đi thực thi được cấp**, thay vì trông đợi việc xóa một biến Java hay drop lookup mode.

## 5. Thực hành Java 17+: chứng minh quyền được kiểm tra lúc nào

Ta tạo hai **named modules**:

- `m.vault` chứa private methods và quyết định cấp quyền.
- `m.app` là client, có `requires m.vault`, nhưng **không** được cấp deep reflection vào package `demo.vault`.

Cấu trúc tệp chính xác:

```text
src/
├── m.vault/
│   ├── module-info.java
│   └── demo/vault/VaultApi.java
└── m.app/
    ├── module-info.java
    └── demo/app/Main.java
```

Ví dụ này dùng **bốn tệp Java**, không phụ thuộc thư viện ngoài. Tệp `module-info.java` cũng được biên dịch cùng mã nguồn còn lại.

**Tệp `src/m.vault/module-info.java`:**

```java
module m.vault {
    exports demo.vault;
}
```

Package được export để consumer dùng public `VaultApi`. Nó **không** được `opens` cho client, nên consumer không tự có quyền deep reflection vào private methods.

**Tệp `src/m.vault/demo/vault/VaultApi.java`:**

```java
package demo.vault;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class VaultApi {
    private static String token() {
        return "TOKEN-42";
    }

    private static String internal() {
        return "INTERNAL";
    }

    public static MethodHandle grantTokenCall()
            throws NoSuchMethodException, IllegalAccessException {
        return MethodHandles.lookup().findStatic(
                VaultApi.class, "token", MethodType.methodType(String.class));
    }

    // PHẢN VÍ DỤ: không xuất full-privilege Lookup trong production.
    public static MethodHandles.Lookup dangerousLookup() {
        return MethodHandles.lookup();
    }

    // Lookup mới được giảm PRIVATE; không ảnh hưởng các handle đã cấp.
    public static MethodHandles.Lookup reducedLookup() {
        return MethodHandles.lookup()
                .dropLookupMode(MethodHandles.Lookup.PRIVATE);
    }
}
```

`grantTokenCall` được gọi từ bên ngoài, nhưng **`MethodHandles.lookup()` nằm trong thân `VaultApi`**, do đó lookup class là `VaultApi`, có quyền tạo handle tới private `token()` của chính class.

`dangerousLookup` được đưa vào để **chứng minh lỗi chia sẻ capability**, tuyệt đối không phải API nên copy vào hệ thống thật.

**Tệp `src/m.app/module-info.java`:**

```java
module m.app {
    requires m.vault;
}
```

Client reads module library và sử dụng public API, nhưng `requires` không tự cấp quyền gọi private method.

**Tệp `src/m.app/demo/app/Main.java`:**

```java
package demo.app;

import demo.vault.VaultApi;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    public static void main(String[] args) throws Throwable {
        var granted = VaultApi.grantTokenCall();
        System.out.println("handle=" + (String) granted.invokeExact());

        // Lookup tạo trong Main không có quyền private của VaultApi.
        try {
            MethodHandles.lookup().findStatic(
                    VaultApi.class, "token",
                    MethodType.methodType(String.class));
            System.out.println("ownLookup=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("ownLookup=denied");
        }

        // Minh họa lỗ hổng: cả private method chưa định cấp cũng được tìm.
        var leaked = VaultApi.dangerousLookup();
        var other = leaked.findStatic(
                VaultApi.class, "internal",
                MethodType.methodType(String.class));
        System.out.println("sharedLookup=" + (String) other.invokeExact());

        // Lookup mới đã giảm quyền không thể mint handle tới internal().
        var narrowed = VaultApi.reducedLookup();
        try {
            narrowed.findStatic(
                    VaultApi.class, "internal",
                    MethodType.methodType(String.class));
            System.out.println("reducedLookup=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("reducedLookup=denied");
        }

        // Handle đã được cấp vẫn gọi được.
        System.out.println("oldHandle=" + (String) granted.invokeExact());
    }
}
```

### 5.1. Biên dịch và chạy

Đứng ở thư mục cha chứa `src`, dùng JDK 17 trở lên:

```bash
javac --release 17 -d mods --module-source-path src src/m.vault/module-info.java src/m.vault/demo/vault/VaultApi.java src/m.app/module-info.java src/m.app/demo/app/Main.java
java --module-path mods -m m.app/demo.app.Main
```

Kết quả đã kiểm chứng bằng cách biên dịch `--release 17` và chạy hai named modules:

```text
handle=TOKEN-42
ownLookup=denied
sharedLookup=INTERNAL
reducedLookup=denied
oldHandle=TOKEN-42
```

### 5.2. Giải nghĩa năm dòng kết quả

1. **`handle=TOKEN-42`:** `VaultApi` đã tạo handle tới private `token()` bằng lookup có quyền; `m.app` nhận reference và gọi thành công mà không cần mở package hay được cấp quyền truy cập trực tiếp tới `token()`.
2. **`ownLookup=denied`:** lookup được tạo trong `Main` chỉ mang quyền của `demo.app.Main`. Dù `m.app` có `requires m.vault`, `exports demo.vault` chỉ cấp access tới public API, không cấp private access. `findStatic` ném `IllegalAccessException`.
3. **`sharedLookup=INTERNAL`:** `Main` nhận **nguyên Lookup của `VaultApi`** qua một public method. Với lookup đó, nó tạo được handle tới **một private method khác (`internal`)** chưa từng được chủ ý cấp. Đây là lý do không rò rỉ lookup đầy quyền.
4. **`reducedLookup=denied`:** `dropLookupMode(PRIVATE)` trả một lookup bị giảm quyền nên không tạo được handle tới private method mới. Không nên suy rằng việc trả một reduced lookup chắc chắn an toàn cho mọi API; cần đánh giá các modes còn lại và quyền public/package/module.
5. **`oldHandle=TOKEN-42`:** handle đã được cấp vẫn hợp lệ. Việc tạo một lookup bị giảm quyền không thu hồi handle cũ, kể cả khi code trao lookup mới cho consumer.

Chú ý: đây là **thí nghiệm về Java access control và capability sharing**, không phải mô hình cấp quyền nghiệp vụ an toàn. Public `grantTokenCall` trong ví dụ đang phát handle cho **bất kỳ caller** nào được phép gọi public API; ứng dụng thật phải có chính sách kiểm soát ai được nhận nó.

## 6. Cơ chế kiểm tra quyền chi tiết trong `Lookup`

### 6.1. Lookup class và lookup modes là hai giới hạn độc lập

Để đánh giá một Lookup:

```java
Class<?> owner = lookup.lookupClass();
int modes = lookup.lookupModes();
boolean full = lookup.hasFullPrivilegeAccess();
```

Đây là đoạn minh họa dùng biến `lookup` đã tồn tại, không phải chương trình độc lập. `lookupClass()` là danh tính dùng trong access checks; `lookupModes()` mô tả các loại quyền còn giữ; `hasFullPrivilegeAccess()` là một phép hỏi tổng quát theo hợp đồng API.

Một `Lookup` có thể giữ lookup class giàu quyền nhưng các mode đã giảm. Ví dụ `VaultApi.reducedLookup()` vẫn gắn với `VaultApi` nhưng không được tạo handle tới private member. Ngược lại, một lookup full privilege của `Main` không tự truy cập private member của `VaultApi` vì nó gắn với **class khác**.

**Không tự suy `lookupModes` bằng một con số cố định** qua mọi phiên bản Java. Dùng tên hằng số và API để kiểm tra; `dropLookupMode` còn có quy tắc loại bỏ các mode phụ thuộc.

### 6.2. `dropLookupMode` tạo đối tượng quyền thấp hơn

`lookup.dropLookupMode(MethodHandles.Lookup.PRIVATE)` trả **Lookup mới**. Mọi tham chiếu đang giữ `lookup` gốc vẫn có quyền của đối tượng gốc.

Quy tắc hạ quyền trong thực tế:

- Chỉ giữ những mức access cần thiết đối với công việc được giao.
- Không trả full lookup từ API public chỉ để giúp client gọi một public member; client có thể dùng `MethodHandles.publicLookup()` khi đúng phạm vi, hoặc một wrapper/factory giới hạn.
- Nếu cung cấp lookup cho framework tin cậy, xem xét `dropLookupMode`, `Lookup.in(...)` và module boundary, đồng thời kiểm tra lại các API mà lookup mới **thực tế có thể** dùng.
- Nếu cần đúng một hành động, trả **handle cụ thể hoặc interface nhỏ** thường dễ kiểm soát hơn là trao công cụ tìm thêm member.

`Lookup.in(SomeClass.class)` cũng có thể làm quyền bị giảm khi chuyển lookup class. Nó **không** tự tăng quyền; khi đi qua module, `previousLookupClass` và các restrictions liên quan còn được tính tới.

### 6.3. `privateLookupIn` khác với xuất lookup gốc

`MethodHandles.privateLookupIn(target, callerLookup)` có thể tạo một lookup trên target class khi các điều kiện được đáp ứng. Với hai named modules khác nhau trên Java 17+, module của caller phải **reads** module đích, package của target phải **opens** tới caller module, và caller lookup phải có `PRIVATE` cùng `MODULE` modes phù hợp.

Nó không phải “mẹo” để consumer thiếu quyền tự lấy private lookup của module khác. Trong ví dụ, `m.vault` chỉ `exports demo.vault`; **không `opens` package**, vì vậy `m.app` không thể tự dùng `privateLookupIn` để đọc các private methods của `VaultApi`.

Nếu chủ sở hữu target **tự trả một `Lookup` full privilege** qua public method, họ đã trực tiếp **ủy quyền capability** đó, bất kể package có `opens` hay không. Đây chính là điểm nguy hiểm: module openness bảo vệ quá trình **tự tìm quyền** qua API, nhưng không thu hồi một capability đã được chủ sở hữu cố ý hoặc vô ý phát ra.

### 6.4. `publicLookup()` và ngoại lệ `UNCONDITIONAL`

`MethodHandles.publicLookup()` có `UNCONDITIONAL` mode, giả định module readability nhưng chỉ tạo handles cho public members của public classes trong package được **export vô điều kiện**.

Vì nó không cấp `PRIVATE`, nó không tìm được `VaultApi.token()` trong ví dụ. Nó có thể phù hợp để tạo các public handles dùng chung khi mục tiêu đúng là public API, nhưng qualified exports và caller-sensitive members cần được cân nhắc riêng.

Không coi `publicLookup` như phương án tự động thay thế mọi lookup: nó có phạm vi hẹp và không có full privilege.

## 7. Trách nhiệm của nơi tạo và nơi nhận quyền

### Bên **tạo/cấp** capability

Chủ sở hữu private member phải quyết định rõ:

1. **Ai được nhận?** Một module được export không đồng nghĩa mọi code được quyền thao tác nội dung bí mật; public factory cần cơ chế authorization nếu target chứa dữ liệu hoặc hành động đặc quyền.
2. **Cấp gì?** Nếu chỉ cần một thao tác, cấp một handle tới **wrapper có phạm vi nhỏ** hoặc API dạng interface; tránh trả `MethodHandles.lookup()` full privilege.
3. **Có cần kiểm tra mỗi lần gọi không?** Nếu quyền dựa trên session, role, quota, feature flag hoặc trạng thái thay đổi, đặt check vào đường gọi thực tế. Kiểm tra duy nhất khi phát handle không đủ để bảo vệ các lần gọi tương lai.
4. **Tài nguyên nào có thể bị ảnh hưởng?** Một private method handle có thể đổi trạng thái, chạy I/O, cấp phát bộ nhớ hoặc gọi hệ thống ngoài. Giới hạn side effects và đầu vào theo hợp đồng của ứng dụng.
5. **Có thể chuyển tiếp hay lưu trữ không?** Java không tự cấm người nhận giữ reference hoặc chuyển handle cho người khác. Hãy thiết kế theo giả định handle có thể tồn tại lâu hơn request ban đầu, trừ khi tầng ứng dụng kiểm soát việc dùng nó.
6. **Độ bền với refactor**: một handle đã liên kết với method gốc không tự biến thành target mới nếu sau đó có thay đổi code hoặc hot reload. Không coi handle như một chuỗi tên tự resolve lại mỗi lần invoke.

### Bên **nhận/sử dụng** capability

- Chỉ gọi trong phạm vi công việc đã được cấp; không suy rằng vì có object Java thì mọi cách dùng đều được phép về mặt nghiệp vụ.
- Không đăng `Lookup`, private `MethodHandle`, hoặc object chứa chúng vào global registry, plugin registry, cache dùng chung, event bus hay logs nếu nơi đó vượt ranh giới tin cậy.
- Kiểm tra `handle.type()` và dùng signature phù hợp; tránh biến lỗi `WrongMethodTypeException` thành lỗi quyền truy cập.
- Không cấp tiếp private capability cho thư viện không tin cậy chỉ vì thư viện cần “một callback”. Cân nhắc wrapper chỉ phơi ra kết quả/hoạt động đã cho phép.
- Không nhầm một handle không thể gọi do sai `MethodType` với một handle bị thu hồi. Type mismatch khác với authorization.

### Quyền tối thiểu: bảng lựa chọn nhanh

| Nhu cầu thật | Đối tượng nên cung cấp | Mức trao quyền |
| --- | --- | --- |
| Bên ngoài gọi public method bình thường | Public method/interface | Không cần private capability |
| Framework đáng tin phải tra cứu một số member theo hợp đồng | `Lookup` đã giới hạn, khi thật sự cần; kiểm tra `lookupModes` | Cần kiểm toán phạm vi có thể tạo handle |
| Consumer chỉ cần gọi một private operation cụ thể | Một `MethodHandle` được cấp có chủ đích hoặc wrapper | Trao quyền gọi target đã chọn |
| Quyền mỗi lần gọi có thể thay đổi theo policy | Wrapper/service kiểm tra policy mỗi lần thực thi | Kiểm soát liên tục tại runtime |
| Cần nhiều thao tác bí mật nội bộ | Giữ full lookup trong module của chủ sở hữu; tạo handles nội bộ | Tránh xuất công cụ cấp quyền vượt boundary |
| Plugin chỉ cần nhận sự kiện | Interface callback công khai và DTO tối thiểu | Không phơi private lookup hay handle |

Nguyên tắc least privilege áp dụng cả với mức **lookup** (quyền tạo thêm handles) và mức **handle** (quyền thực thi một target). Đánh giá đồng thời hai mức mới tránh nhầm lẫn.

## 8. Thu hồi quyền và kiểm tra ở mỗi lần gọi

Một sai lầm rất phổ biến là:

> “Tôi đã ngừng cấp `Lookup`, nên các private method handles phát trước đó sẽ mất tác dụng.”

Không đúng. Handle đã được tạo là một reference khả dụng, không tự hết hạn vì factory ngừng hoạt động. `dropLookupMode` hạ quyền **một Lookup mới**; nó không biết ai đã giữ handle cũ để thu hồi. Việc thay đổi exports/opens hoặc chính sách cấp quyền sau thời điểm tạo cũng không nên được giả định là hủy mọi handle đang tồn tại.

Nếu ứng dụng yêu cầu revocation, có thể triển khai một **wrapper kiểm tra policy ở mỗi lần gọi**. Pseudocode sau minh họa logic nghiệp vụ, **không phải một chương trình Java độc lập**:

```java
String guardedOperation(Request request) {
    if (!policy.isAllowed(request.actor(), request.operation())) {
        throw new SecurityException("Operation denied");
    }
    return internalOperation(request);
}
```

Nếu handle trỏ tới `guardedOperation`, code policy được chạy khi target thực thi. Nhưng nếu bên ngoài còn giữ handle trực tiếp tới `internalOperation`, họ có thể bỏ qua wrapper. Do đó, **đừng phát handle không có guard** rồi hy vọng một guard khác sẽ bảo vệ được nó.

Những cơ chế có thể dùng tùy kiến trúc: interface facade, authorization service, object capability có trạng thái sống/chết, quota, deadline hoặc proxy được kiểm tra tại mỗi invocation. Để thật sự thu hồi, cần một nơi mà **mọi đường gọi đã cấp** bắt buộc đi qua check. Nếu dữ liệu nhạy cảm đã được trả về trước khi thu hồi, Java không thể lấy lại bản sao dữ liệu đó.

`MethodHandle` không phải primitive dành riêng cho bảo mật: nó là công cụ invocation có quyền truy cập ngôn ngữ được kiểm tra lúc tạo. Chính ứng dụng chịu trách nhiệm về authentication, authorization, audit và vòng đời capability.

## 9. Những vấn đề liên quan cần phân biệt

### 9.1. `invoke` và `invokeExact` không kiểm tra lại quyền private, nhưng vẫn kiểm tra type

`invokeExact` yêu cầu exact method type tại call site. `invoke` cho phép một số adaptation kiểu theo quy tắc `MethodHandle`, nhưng không đồng nghĩa với việc mọi chuỗi ký tự hoặc mọi object đều được tự chuyển sang đúng kiểu.

Những exception như `WrongMethodTypeException`, `ClassCastException`, `NullPointerException` hoặc exception do target ném là những lỗi khác với `IllegalAccessException` khi **tạo** handle. Chỗ phát sinh exception rất quan trọng khi debug.

### 9.2. Instance handles vẫn cần receiver phù hợp

Một private instance method handle có thể yêu cầu receiver là object thuộc đúng class hoặc subtype tương thích (tùy handle và cách adapter được tạo). Cấp handle không tự cấp object nhận; nhưng nếu consumer có receiver thích hợp hoặc handle đã được `bindTo` receiver, họ có thể kích hoạt thao tác được cấp.

`bindTo`, `insertArguments`, `asType`, `filterArguments` và các combinator khác có thể thay hình dạng call site hoặc cố định argument. Chúng không tự cho consumer quyền tìm một private method thứ hai, nhưng có thể thay đổi việc dùng handle đã được trao. Vì thế thiết kế cấp handle cần xét cả dữ liệu và đối tượng mà handle có thể tác động.

### 9.3. `VarHandle` cũng mang tính capability

`Lookup.findVarHandle` và `findStaticVarHandle` tạo `VarHandle` cho field khi lookup có quyền. Khi cấp `VarHandle` tới private field, người nhận có thể thực hiện những access modes mà VarHandle, field type, modifier và runtime cho phép. Đừng cho rằng nó chỉ là metadata đọc được.

Ví dụ final field không tự nhiên writable chỉ vì được trả `VarHandle`. Với mutable field, người nhận có thể thấy thêm các thao tác concurrency/memory access; hãy cân nhắc kỹ khi phơi capability này.

### 9.4. Caller-sensitive methods cần thận trọng thêm

Một số Java API là **caller-sensitive**, tức hành vi của chúng phụ thuộc caller được nhận diện theo quy tắc runtime. Khi tạo method handle tới những API ấy, `Lookup` có quy tắc riêng về caller context; `publicLookup()` không phải lúc nào cũng được dùng để tạo handle như vậy.

Vì thế không nên giả định một handle tới mọi public API đều có hành vi giống hệt mã Java gọi trực tiếp từ bất kỳ client nào. Đối với framework cấp method handles để dùng lại, kiểm tra rõ API có caller-sensitive behavior hay không.

### 9.5. Cấp `Lookup` không có nghĩa quyền của recipient được cộng thêm tùy ý

Một Lookup là capability có **quyền được ghi nhận**. Client nhận full Lookup của `VaultApi` có thể dùng quyền của lookup class đó, nhưng không tự động hợp nhất với full privilege của client để có “siêu quyền” của cả hai module. `Lookup.in`, `privateLookupIn` và điều kiện module vẫn xác định chính xác giới hạn của các lookup sinh ra tiếp theo.

Dù vậy, quyền vốn có của lookup gốc đã đủ nguy hiểm nếu nó cho phép tra cứu thêm private members mà provider không chủ định cấp.

## 10. Cách debug và kiểm toán khi thấy private handle chạy được ở nơi “không có quyền”

Khi một private method được gọi thành công từ class không thể compile lời gọi trực tiếp, hãy xác định:

1. **Handle được tạo ở đâu?** Tìm factory như `findStatic`, `findVirtual`, `unreflect` hoặc các adapter; đừng chỉ nhìn vị trí `invokeExact`.
2. **`Lookup` có nguồn từ đâu?** Có phải `MethodHandles.lookup()` ở class có quyền private, `privateLookupIn`, hay một object lookup được truyền từ module khác?
3. **Lookup class và modes là gì?** Xem `lookupClass()`, `lookupModes()`, `previousLookupClass()` khi thích hợp; tránh ghi log thông tin không cần thiết về hệ thống nội bộ.
4. **Đã chia sẻ đối tượng nào?** Full `Lookup`, reduced `Lookup`, hay một handle cụ thể? Một full lookup có thể tạo thêm private handles sau này.
5. **Trước đó đã có access check thành công?** Nếu có, việc invoke từ class ít quyền **không tự chứng minh** lỗi JVM; đó là ngữ nghĩa capability được Java thiết kế.
6. **Target có tự kiểm tra chính sách không?** Nếu target không kiểm tra quyền mỗi lần gọi, quyết định cấp handle ban đầu là điểm kiểm soát chính.
7. **Có reference phát tán không?** Kiểm tra cache, registry, plugin hooks, lambda capture và các APIs trả về những đối tượng này.
8. **Lỗi có thật sự là access không?** Phân biệt `IllegalAccessException` lúc tạo handle với `WrongMethodTypeException`/exception từ target khi invoke.
9. **Cần sửa ở đâu?** Thu hẹp factory và contract cấp quyền, bọc target bằng policy check, hạn chế receiver/argument hoặc giữ mọi handle có quyền trong module tin cậy.

Đừng cố giải quyết bằng cách thêm `--add-opens` hoặc gọi `setAccessible(true)` trước khi xác định được nơi quyền đã được cấp. Các flags đó giải quyết vấn đề module access ở những tình huống nhất định, nhưng **không** giải quyết việc nhà cung cấp chủ động rò rỉ một `Lookup` hoặc handle.

## 11. Các lỗi tư duy thường gặp

| Kết luận sai | Sự thật cần nhớ |
| --- | --- |
| “Caller không thấy private method nên không thể gọi handle.” | Nếu đã nhận handle hợp lệ, caller có thể invoke mà không cần tự lookup lại private member |
| “Đưa `Lookup` vào API public chỉ giống đưa một `MethodHandle`.” | Lookup có thể tạo thêm handles cho những members khác trong phạm vi quyền của nó |
| “`MethodHandles.lookup()` trả quyền của người nhận sau khi truyền qua method.” | Lookup ghi nhận class gọi `lookup()` tại lúc được tạo |
| “`dropLookupMode` sửa luôn Lookup cũ.” | Nó trả Lookup mới với quyền bị giảm |
| “Giảm quyền Lookup sẽ vô hiệu hóa handles đã phát.” | Handles đã tạo không tự bị thu hồi |
| “Phát một private handle là hoàn toàn an toàn vì chỉ gọi được một method.” | Target có thể chứa logic nhạy cảm hoặc tác dụng phụ; consumer có thể gọi nhiều lần và chuyển tiếp handle |
| “MethodHandle bỏ mọi kiểm tra Java.” | Chỉ language access đã được xử lý khi tạo; method type và logic của target vẫn áp dụng |
| “Reflection và MethodHandle luôn kiểm tra ở cùng thời điểm.” | `Method.invoke` thường kiểm tra quyền của caller ở lần gọi; MethodHandle factory kiểm tra lúc tạo |
| “Chỉ cần export public API là client có thể tự lấy private Lookup.” | `exports` không đồng nghĩa `opens` hay quyền private |
| “Nếu `invokeExact` lỗi thì chắc chắn thiếu access.” | Lỗi call-site type có thể xảy ra sau khi handle hợp lệ đã được tạo |

## 12. Tự kiểm tra cuối bài

1. `VaultApi.grantTokenCall()` được gọi từ `Main`. Lookup class của `MethodHandles.lookup()` trong method ấy là gì? **`VaultApi`**, vì nơi gọi `lookup()` nằm trong `VaultApi`.
2. Vì sao `Main` có thể gọi `granted.invokeExact()` nhưng không tự `findStatic` private `token()`? **Handle đã được provider cấp hợp lệ; tự tìm lại method là một access check mới dùng lookup của `Main`.**
3. Vì sao `VaultApi.dangerousLookup()` nguy hiểm hơn `grantTokenCall()`? **Nó cho client quyền tạo các handles khác, ví dụ tới `internal()`.**
4. `dropLookupMode(PRIVATE)` trên một lookup có thu hồi các handles đã cấp bằng lookup gốc không? **Không.**
5. `m.app` có `requires m.vault` và package được `exports`; điều đó tự cấp private access không? **Không.**
6. Nếu muốn ngăn user đã hết phiên gọi tiếp một handle, nên đặt chính sách ở đâu? **Trong đường thực thi mà mọi lời gọi đã cấp đều đi qua, ví dụ wrapper được kiểm tra mỗi lần, đồng thời không để lộ raw bypass handle.**
7. `invokeExact()` ném `WrongMethodTypeException` có chứng minh private access bị từ chối không? **Không; lỗi này liên quan call-site type.**
8. Khi chia sẻ `Lookup`, có thể coi quyền tự động chuyển sang class nhận không? **Không; lookup class và modes vẫn gắn với đối tượng đã tạo.**
9. Khi một thư viện chỉ cần public method, vì sao `publicLookup()` hoặc public interface thường phù hợp hơn full lookup? **Chúng thu hẹp quyền vào API công khai, tránh trao capability tạo private handles.**
10. Một private method handle là “an toàn” chỉ vì `MethodType` không có tham số không? **Không; method không có tham số vẫn có thể đọc dữ liệu nhạy cảm hoặc gây side effects.**

## 13. Tài liệu chính thống

- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): mục Access checking và khả năng invoke từ caller nhận handle.
- [Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, `privateLookupIn` và caller-sensitive behavior.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup class, access modes, thời điểm factory access checks, `dropLookupMode`, `in`, `find*`.
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): chữ ký tham số/kiểu trả về của method handle.
- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): access checks và `setAccessible`/`trySetAccessible` của Core Reflection.

**Quy tắc vận dụng:** Hãy coi **tạo `Lookup` → dùng `Lookup` mint handle → chia sẻ handle → thực thi handle** là các bước phân quyền riêng. Access của private member được xét chủ yếu **khi mint handle**; phía sau, handle là một quyền thực thi đã được trao. Muốn bảo vệ hệ thống, kiểm soát cả **người được cấp, phạm vi capability, vòng đời và chính sách kiểm tra mỗi lần dùng**.