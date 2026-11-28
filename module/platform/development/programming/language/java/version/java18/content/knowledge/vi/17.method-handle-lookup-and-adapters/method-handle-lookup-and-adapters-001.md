# Lookup như năng lực truy cập: lookupClass(), lookupModes() và thời điểm kiểm tra quyền

## Mục tiêu bài học

Trong chương **Lookup và adapter** của mô-đun Java 18, đối tượng `java.lang.invoke.MethodHandles.Lookup` là chìa khóa để tìm và tạo `MethodHandle`. Một `Lookup` không đơn thuần là công cụ tìm phương thức theo tên: nó đại diện cho **năng lực truy cập** của một ngữ cảnh Java cụ thể, chịu các quy tắc visibility và Java Platform Module System (JPMS).

Sau bài học, bạn có thể:

- Giải thích `lookup.lookupClass()` cho biết **lớp đại diện cho ngữ cảnh lookup** và vì sao lớp đó quan trọng.
- Đọc `lookup.lookupModes()` bằng cách kiểm tra các **bit quyền**, thay vì coi giá trị trả về là một cấp độ truy cập duy nhất.
- Phân biệt `MethodHandles.lookup()`, `MethodHandles.publicLookup()`, `Lookup.in(...)` và `MethodHandles.privateLookupIn(...)`.
- Chỉ ra **thời điểm Java kiểm tra quyền để tìm member và tạo handle**, cùng những kiểm tra kiểu và lỗi vẫn có thể xảy ra khi gọi handle sau này.
- Chạy ví dụ trên class path và trong hai named modules để quan sát khác biệt giữa `exports` và `opens`.
- Thiết kế cách trao `Lookup` cho thư viện/plugin với quyền tối thiểu, tránh vô tình làm lộ quyền truy cập private.

> **Phạm vi hiện hành:** `java.lang.invoke` là API chuẩn vẫn được hỗ trợ trên các JDK hiện đại. Java 18 có JEP 416 dùng method handles làm cơ sở triển khai core reflection; bài này tập trung vào **hợp đồng riêng của `MethodHandles.Lookup`**, không dựa vào lớp nội bộ JDK, quyền truy cập không được cấp hoặc cơ chế đã lỗi thời.

## 1. Tư duy đúng: `Lookup` là năng lực truy cập

Khi viết Java thông thường, trình biên dịch kiểm tra mã có được phép gọi method, truy cập field hay tạo đối tượng hay không. Với Method Handle API, ta thường **tìm member lúc chạy**:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();

MethodHandle handle = lookup.findVirtual(
        Account.class,
        "displayName",
        MethodType.methodType(String.class));
~~~

Lệnh `findVirtual(...)` không chỉ tìm tên `displayName`. Nó còn kiểm tra những điều kiện phù hợp với quyền của đối tượng `lookup`: lớp đích, member, kiểu, quan hệ truy cập và ranh giới module.

Nếu thành công, ta nhận được một `MethodHandle` có thể được dùng để gọi member tương ứng. **Handle được cấp dựa trên quyền hợp lệ tại thời điểm tạo**; thông thường lời gọi tiếp theo trên cùng handle không yêu cầu lặp lại toàn bộ phép kiểm tra quyền truy cập Java đã dùng để tạo handle.

Nếu lookup không được phép truy cập member, thao tác tìm có thể báo `IllegalAccessException`. Một lời tìm sai tên/chữ ký có thể báo `NoSuchMethodException` hoặc `NoSuchFieldException` tùy API. Điều này khác với lỗi kiểu tại điểm gọi hoặc ngoại lệ do chính method đích ném sau khi handle đã được tạo.

### Vì sao gọi là “năng lực”?

Đối tượng `Lookup` mang ngữ cảnh truy cập, nên **chuyển một lookup có quyền cao cho đoạn mã khác có thể chuyển khả năng tạo những handle mà đoạn mã ấy không tự tạo được**. Chẳng hạn, một thư viện nhận `Lookup` có quyền private phù hợp có thể dùng nó để tìm private member trong phạm vi được phép.

Không nên thiết kế API plugin yêu cầu truyền `MethodHandles.lookup()` có đầy đủ quyền chỉ để tìm các public method. Hãy cấp một lookup phù hợp với công việc, hoặc tốt hơn là trao đúng `MethodHandle` đã được kiểm soát.

### Hai việc khác nhau

| Thao tác | Câu hỏi Java phải giải quyết | Thời điểm |
| --- | --- | --- |
| `lookup.findStatic(...)`, `findVirtual(...)`, `findGetter(...)`, `findConstructor(...)` | Có tìm đúng member và được phép tạo handle tới member này không? | Khi tìm/tạo handle |
| `handle.invokeExact(...)` hoặc `handle.invoke(...)` | Điểm gọi có kiểu phù hợp với handle không? Method đích có thực thi thành công không? | Khi gọi handle |
| `handle.asType(...)`, `bindTo(...)` hoặc adapter khác | Có thể xây handle mới với chữ ký/thao tác điều chỉnh hợp lệ không? | Khi tạo adapter, và có thể còn chuyển đổi giá trị lúc gọi |
| `lookup.lookupClass()`, `lookup.lookupModes()` | Lookup hiện đại diện cho ngữ cảnh lớp nào và những bit quyền nào? | Khi truy vấn đối tượng lookup |

**Lưu ý:** “đã kiểm tra quyền khi tạo handle” không có nghĩa lần gọi sau sẽ luôn thành công. Chữ ký ở điểm gọi, ép kiểu dữ liệu, việc khởi tạo lớp và ngoại lệ của method đích vẫn được xử lý theo hợp đồng tương ứng.

## 2. `lookupClass()`: lookup đại diện cho lớp nào?

Chữ ký:

~~~java
public Class<?> lookupClass()
~~~

`lookup.lookupClass()` trả về lớp đại diện cho **ngữ cảnh của đối tượng lookup**. Đây là một yếu tố để Java quyết định quyền truy cập, đặc biệt với các member không public.

Ví dụ:

~~~java
MethodHandles.Lookup local = MethodHandles.lookup();

System.out.println(local.lookupClass().getName());
~~~

Nếu dòng `MethodHandles.lookup()` nằm trực tiếp trong lớp `demo.app.Main`, kết quả là `demo.app.Main`. Phương thức `MethodHandles.lookup()` có hành vi phụ thuộc **lớp chứa lời gọi thực tế** (*caller-sensitive*); không nên nghĩ rằng nó luôn lấy lớp của đối tượng được truyền vào một helper.

Giả sử một thư viện có:

~~~java
final class LookupFactory {
    static MethodHandles.Lookup create() {
        return MethodHandles.lookup();
    }
}
~~~

Khi code ứng dụng gọi `LookupFactory.create()`, `lookupClass()` của đối tượng trả về là `LookupFactory.class`, **không phải** lớp ứng dụng gọi `create()`. Bọc `MethodHandles.lookup()` vào tiện ích có thể thay đổi ngữ cảnh quyền mà ứng dụng mong muốn.

### `lookupClass()` không đủ để kết luận được truy cập member

Hai đối tượng `Lookup` có thể cùng `lookupClass()` nhưng mang các **lookup modes khác nhau**. Việc chỉ in tên lớp rồi kết luận “đủ quyền private” là sai.

Muốn đánh giá lookup, cần xem **cả** `lookupClass()`, `lookupModes()` và **member/package/module cụ thể** được truy cập.

## 3. `lookupModes()`: tập quyền được biểu diễn dưới dạng bitmask

Chữ ký:

~~~java
public int lookupModes()
~~~

Giá trị `int` là **bitmask** của các chế độ truy cập được lookup sở hữu. Một số cờ thường gặp trên JDK hiện đại:

| Cờ trong `MethodHandles.Lookup` | Vai trò khái quát |
| --- | --- |
| `PUBLIC` | Quyền truy cập theo quy tắc public trong phạm vi tương ứng |
| `PRIVATE` | Khả năng truy cập private trong phạm vi được phép |
| `PROTECTED` | Khả năng truy cập protected theo quan hệ hợp lệ |
| `PACKAGE` | Khả năng truy cập package-private trong phạm vi phù hợp |
| `MODULE` | Ngữ cảnh quyền liên quan đến module, cần cho một số thao tác mở rộng lookup |
| `UNCONDITIONAL` | Quyền truy cập public theo quy tắc unconditional của lookup công khai |

Các bản JDK có thể có thêm cờ theo hợp đồng API của phiên bản đó. **Không được coi bảng là danh sách mọi bit trên mọi JDK.** Quan trọng hơn, các cờ không phải thứ tự “public < protected < private” để so sánh số học.

Kiểm tra một bit bằng phép AND:

~~~java
import java.lang.invoke.MethodHandles;

static boolean hasPrivateMode(MethodHandles.Lookup lookup) {
    return (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
}
~~~

Cách này đúng với `lookupModes()` là bitmask. Không nên kiểm tra bằng cách so sánh toàn bộ giá trị `lookupModes() == MethodHandles.Lookup.PRIVATE`: lookup có thể đồng thời mang nhiều bit.

### Bit quyền không phải giấy phép cho *mọi* member

Ngay cả khi lookup có `PRIVATE`, nó **không tự động được đọc private method của mọi lớp trong mọi module**. Java còn đánh giá lớp đích, quan hệ module, visibility và những điều kiện đặc thù của member.

Tương tự, lookup không mang bit `PRIVATE` vẫn có thể tìm **public method** phù hợp. Trong các phiên bản JDK hỗ trợ `UNCONDITIONAL`, cách nhìn các bit của `publicLookup()` có sắc thái riêng: hãy dựa vào **khả năng truy cập được tài liệu hóa**, không suy luận chỉ từ một bit `PUBLIC`.

Nếu cần biết lookup có toàn bộ quyền tương ứng với ngữ cảnh của chính nó hay không, JDK hiện đại còn có `Lookup.hasFullPrivilegeAccess()`. Kết quả này cũng **không phải** quyền truy cập private tự do xuyên tất cả module.

## 4. Những cách lấy hoặc biến đổi `Lookup`

### `MethodHandles.lookup()`

~~~java
MethodHandles.Lookup local = MethodHandles.lookup();
~~~

Tạo lookup đại diện cho lớp đang thực sự gọi phương thức này. Khi dùng trực tiếp trong lớp ứng dụng thông thường, lookup có quyền đầy đủ thích hợp với lớp gọi. Nó có thể dùng để tìm member private mà mã từ lớp đó có quyền truy cập, nhưng vẫn chịu ràng buộc JPMS và các quy tắc Java.

### `MethodHandles.publicLookup()`

~~~java
MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
~~~

Tạo lookup dành cho truy cập công khai. Đây là lựa chọn phù hợp khi thư viện chỉ cần tìm member public của các lớp public có khả năng truy cập hợp lệ, chẳng hạn trong package được export công khai.

`publicLookup()` **không** cấp quyền đọc private method chỉ vì người gọi biết tên method.

### `lookup.in(Target.class)`

~~~java
MethodHandles.Lookup moved = local.in(Target.class);
~~~

Tạo đối tượng lookup với **lookup class mới**. Quan hệ giữa lớp ban đầu, lớp đích và các module có thể khiến lookup mới **mất một số quyền**. `in(...)` không phải cách lấy private access tùy ý sang lớp khác.

Do đó:

~~~java
System.out.println(local.lookupClass());
System.out.println(local.lookupModes());

System.out.println(moved.lookupClass());
System.out.println(moved.lookupModes());
~~~

Hãy quan sát cả hai thông tin, đặc biệt trước khi tìm member không public. Không giả định `moved.lookupModes()` giống `local.lookupModes()`.

### `lookup.dropLookupMode(mode)`

Đây là cách tạo một lookup **ít quyền hơn** theo quy tắc API:

~~~java
MethodHandles.Lookup restricted =
        local.dropLookupMode(MethodHandles.Lookup.PRIVATE);
~~~

Khi hạ một chế độ, các chế độ liên quan cũng có thể bị giảm theo quy tắc JDK. Vì vậy, phải đọc `restricted.lookupModes()` sau khi tạo; không tự suy luận nó chỉ khác đúng một bit.

Nếu giao lookup cho bên nhận chỉ cần quyền public, `publicLookup()` là cách thể hiện ý định rõ ràng hơn việc tự chế một công thức bitmask.

### `MethodHandles.privateLookupIn(Target.class, callerLookup)`

~~~java
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(Target.class, local);
~~~

API này có thể tạo lookup có khả năng truy cập private của **lớp đích** khi các điều kiện được đáp ứng.

Đặc biệt:

- `callerLookup` phải có quyền cần thiết; theo hợp đồng thông thường, nó cần cả chế độ `PRIVATE` và `MODULE`.
- Nếu chuyển sang **module khác**, package chứa lớp đích phải được **mở cho module của lookup gọi** theo quy tắc JPMS. Chỉ `exports` thường không đủ cho truy cập private sâu.
- Nếu các điều kiện không đáp ứng, thao tác có thể báo `IllegalAccessException`.
- Khi thành công, `deep.lookupClass()` là lớp đích. Các lookup modes của nó phản ánh quyền được cấp theo quan hệ giữa các lớp/module; không nên giả định luôn giữ mọi quyền của `callerLookup`.

**Điểm mấu chốt:** `privateLookupIn` không phải lệnh phá đóng gói. Nó thực hiện cơ chế **chuyển ngữ cảnh lookup có kiểm soát** khi chủ sở hữu module đã cấp quyền phù hợp.

## 5. Ví dụ 1: kiểm tra lớp, mode và thời điểm chặn truy cập

Ví dụ đầu tiên chạy trên **class path** để tập trung vào cách lấy lookup và thời điểm kiểm tra quyền. Tạo file `LookupCapabilityDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupCapabilityDemo {
    public static final class Vault {
        private static String secret() {
            return "secret-42";
        }

        public static String greet(String name) {
            return "Hello " + name;
        }
    }

    private static final class Helper {
        static MethodHandles.Lookup createLookup() {
            return MethodHandles.lookup();
        }
    }

    static boolean hasPrivate(MethodHandles.Lookup lookup) {
        return (lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup local = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();
        MethodHandles.Lookup fromHelper = Helper.createLookup();

        System.out.println("local class=" +
                local.lookupClass().getSimpleName());
        System.out.println("helper class=" +
                fromHelper.lookupClass().getSimpleName());

        System.out.println("local private=" + hasPrivate(local));
        System.out.println("public private=" + hasPrivate(publicOnly));

        MethodType oneString =
                MethodType.methodType(String.class, String.class);
        MethodType noArgs = MethodType.methodType(String.class);

        // Public API: lookup thanh cong.
        MethodHandle greet =
                publicOnly.findStatic(Vault.class, "greet", oneString);

        System.out.println((String) greet.invokeExact("Lan"));

        // Private API: public lookup bi tu choi khi TIM handle.
        try {
            publicOnly.findStatic(Vault.class, "secret", noArgs);
            throw new AssertionError("Khong duoc cap private access");
        } catch (IllegalAccessException expected) {
            System.out.println("public cannot find private");
        }

        // Chuyen lookup hop le trong cung module.
        MethodHandles.Lookup deep =
                MethodHandles.privateLookupIn(Vault.class, local);

        System.out.println("deep class=" +
                deep.lookupClass().getSimpleName());
        System.out.println("deep private=" + hasPrivate(deep));

        MethodHandle secret =
                deep.findStatic(Vault.class, "secret", noArgs);

        System.out.println((String) secret.invokeExact());
    }
}
~~~

Biên dịch, chạy trong JDK 18 trở lên:

~~~sh
javac LookupCapabilityDemo.java
java LookupCapabilityDemo
~~~

Kết quả dự kiến:

~~~text
local class=LookupCapabilityDemo
helper class=Helper
local private=true
public private=false
Hello Lan
public cannot find private
deep class=Vault
deep private=true
secret-42
~~~

### Vì sao ví dụ có ý nghĩa?

1. `local.lookupClass()` là `LookupCapabilityDemo` vì lời gọi `MethodHandles.lookup()` xuất hiện trong `main` của lớp này.
2. `fromHelper.lookupClass()` là `Helper`, chứng minh helper không tự kế thừa danh tính caller bên ngoài.
3. `publicOnly.findStatic(Vault.class, "greet", ...)` thành công do `Vault` và `greet` là public trong ví dụ trên class path.
4. `publicOnly.findStatic(Vault.class, "secret", ...)` thất bại **ngay lúc tìm handle** vì lookup công khai không có quyền private.
5. `privateLookupIn(Vault.class, local)` tạo lookup thích hợp trong cùng module (unnamed module của ứng dụng trên class path). Sau đó `deep.findStatic` mới có thể tìm private method.
6. Khi `secret` đã được tạo hợp lệ, `secret.invokeExact()` gọi method; không có thao tác xin lại quyền private riêng tại mỗi lần gọi.

**Đừng suy diễn từ ví dụ class path sang named module.** Khi đặt các lớp vào module có đóng gói mạnh, các quy tắc đọc module, `exports` và `opens` phải được kiểm tra riêng.

## 6. Ví dụ 2: hai named modules, `exports` chưa đủ cho private lookup

Ví dụ này tách rõ **truy cập public hợp lệ** và **truy cập sâu private bị từ chối**.

### Cấu trúc thư mục

~~~text
src/
  sample.library/
    module-info.java
    sample/api/TokenBox.java
  sample.client/
    module-info.java
    sample/client/Client.java
~~~

File `src/sample.library/module-info.java`:

~~~java
module sample.library {
    exports sample.api;
}
~~~

File `src/sample.library/sample/api/TokenBox.java`:

~~~java
package sample.api;

public final class TokenBox {
    public static String name() {
        return "public-info";
    }

    private static String token() {
        return "internal-token";
    }
}
~~~

File `src/sample.client/module-info.java`:

~~~java
module sample.client {
    requires sample.library;
}
~~~

File `src/sample.client/sample/client/Client.java`:

~~~java
package sample.client;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import sample.api.TokenBox;

public final class Client {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup caller = MethodHandles.lookup();
        MethodHandles.Lookup onlyPublic =
                MethodHandles.publicLookup();

        MethodType resultString =
                MethodType.methodType(String.class);

        MethodHandle name = onlyPublic.findStatic(
                TokenBox.class, "name", resultString);

        System.out.println((String) name.invokeExact());

        try {
            MethodHandles.Lookup deep =
                    MethodHandles.privateLookupIn(TokenBox.class, caller);

            MethodHandle token = deep.findStatic(
                    TokenBox.class, "token", resultString);

            System.out.println((String) token.invokeExact());
        } catch (IllegalAccessException denied) {
            System.out.println("private lookup denied");
        }
    }
}
~~~

Biên dịch:

~~~sh
javac --module-source-path src -d out -m sample.library,sample.client
~~~

Chạy khi thư viện **chỉ export** package:

~~~sh
java --module-path out -m sample.client/sample.client.Client
~~~

Kết quả mong đợi:

~~~text
public-info
private lookup denied
~~~

Điểm từ chối nằm ở `privateLookupIn(...)`: `sample.api` đã được `exports`, nên API public có thể được tìm và gọi; nhưng package đó **chưa được mở** cho deep reflection từ `sample.client`.

### Mở đúng package cho module cần truy cập

Với môi trường thử nghiệm, có thể chạy cùng chương trình bằng:

~~~sh
java --module-path out --add-opens sample.library/sample.api=sample.client -m sample.client/sample.client.Client
~~~

Kết quả dự kiến:

~~~text
public-info
internal-token
~~~

Tùy chọn `--add-opens` là một cách minh họa quyền mở package tại **thời điểm khởi chạy JVM**. Nếu bạn quản lý source của module thư viện và chủ động cung cấp cơ chế extension, một lựa chọn rõ hơn có thể là khai báo trong `module-info.java`:

~~~java
module sample.library {
    exports sample.api;
    opens sample.api to sample.client;
}
~~~

Sau đó biên dịch lại module. Ưu tiên mở **đúng package và đúng module cần truy cập**; tránh cung cấp quyền deep reflection rộng hơn nhu cầu ứng dụng.

### Quyền được kiểm tra ở đâu trong ví dụ hai module?

~~~text
Client co Lookup tu MethodHandles.lookup()
       |
       +--> publicLookup.findStatic(TokenBox.name)
       |       |
       |       +--> Duoc phep: public class + public method + exports
       |                      --> tao MethodHandle
       |
       +--> privateLookupIn(TokenBox, caller)
               |
               +--> sample.api chua opens cho sample.client
               |       --> IllegalAccessException tai buoc tao Lookup
               |
               +--> sample.api da opens cho sample.client
                       --> tao deep Lookup hop le
                            |
                            +--> deep.findStatic(TokenBox.token)
                                   --> tao MethodHandle
                                        |
                                        +--> invokeExact()
                                             --> chay method dich
~~~

Quyền khi tạo lookup/handle và lỗi khi chạy method là hai tầng khác nhau. Chú ý `privateLookupIn` có thể bị từ chối **trước** khi code đi tới `findStatic`, còn `findStatic` cũng thực hiện kiểm tra riêng trên member đích với quyền của `deep`.

## 7. Thời điểm kiểm tra quyền: khi tạo handle, không phải cách gọi lại mỗi lần

Đây là điểm quan trọng nhất của bài học.

Trong luồng sử dụng thông thường:

1. **Tạo lookup:** lấy `MethodHandles.lookup()`, `publicLookup()` hoặc chuyển ngữ cảnh bằng `privateLookupIn(...)`. Quyền của lookup bị giới hạn theo cách tạo và mối quan hệ giữa các lớp/module.
2. **Tìm member và tạo handle:** `findVirtual`, `findStatic`, `findConstructor`, `findGetter` hoặc thao tác tương ứng giải quyết tên/chữ ký, đánh giá quyền và trả handle hợp lệ; nếu không, báo lỗi.
3. **Gọi handle:** `invokeExact` hoặc `invoke` kiểm tra kiểu điểm gọi/chuyển đổi theo hợp đồng của method handle, sau đó thực thi member đích. Việc gọi lại cùng handle **không tự làm lại bước `find*` và không yêu cầu lookup ban đầu có mặt**.
4. **Tạo adapter:** `asType`, `bindTo`, `filterArguments`... tạo handle kết hợp dựa trên handle đã có, đồng thời áp dụng quy tắc kiểu/adaptation tương ứng. Chúng không biến member vốn bị từ chối thành được truy cập chỉ bằng đổi chữ ký.

Ví dụ:

~~~java
MethodHandle direct = deep.findStatic(
        TokenBox.class, "token", MethodType.methodType(String.class));

MethodHandle adapted = direct.asType(
        MethodType.methodType(Object.class));

System.out.println((Object) adapted.invokeExact());
~~~

Đoạn mã ở trên đặt trong **ngữ cảnh của ví dụ đã có `deep` hợp lệ**. `adapted` là handle mới trả `Object` và không thêm quyền private nào; việc tìm `TokenBox.token` đã được kiểm tra trước khi tạo `direct`. Đổi kiểu trả về bằng `asType` cũng không thay đổi phần thân method đích.

### Những điều vẫn có thể làm lời gọi thất bại

- `WrongMethodTypeException`: kiểu tham số hoặc kiểu trả về tại điểm gọi `invokeExact` không khớp `handle.type()`.
- `ClassCastException` hoặc lỗi chuyển đổi khác: adapter/`invoke` phải chuyển giá trị runtime không tương thích.
- `NullPointerException` hoặc lỗi do receiver/đối số cụ thể không hợp lệ.
- Ngoại lệ do phương thức đích chủ động ném: Method Handle thông thường truyền ngoại lệ đó ra theo hợp đồng, không tự bọc giống `Method.invoke` của core reflection.
- Lỗi khởi tạo lớp hoặc lỗi liên kết/runtime đặc thù: việc tạo handle thành công không chứng minh toàn bộ quá trình chạy tương lai không có lỗi.

Vì thế, **kiểm tra quyền khi tìm** và **kiểm tra kiểu/giá trị khi gọi** phải được thiết kế và kiểm thử riêng.

### Nếu sau đó thay đổi đối tượng `Lookup` thì sao?

`Lookup` không phải một nút điều khiển để thu hồi hàng loạt các handle đã phát hành. Việc tạo một lookup khác với quyền thấp hơn (ví dụ `dropLookupMode`) **không tự hủy** các MethodHandle hợp lệ đã tạo trước đó.

Muốn giới hạn thứ bên nhận có thể gọi, hãy kiểm soát **lookup hoặc handle được cấp ngay từ đầu**. Đừng trao một handle nhạy cảm rồi kỳ vọng sau đó hạ quyền của đối tượng lookup sẽ vô hiệu hóa handle đã trao.

## 8. Quy tắc thiết kế khi viết API framework/plugin

Một hệ thống plugin, serialization framework hoặc engine chạy kịch bản có thể cần thao tác động. Những quy tắc sau giúp thể hiện rõ quyền:

| Nhu cầu thực tế | Cách tiếp cận nên cân nhắc |
| --- | --- |
| Plugin chỉ cần gọi public API đã xuất | Dùng `publicLookup()` hoặc trao sẵn các handle public cần thiết |
| Mã trong cùng module được chủ sở hữu cho phép dùng private member | Dùng lookup có quyền hợp lệ, chỉ trong đoạn mã được tin cậy |
| Module khác cần deep reflection | Chủ sở hữu module khai báo `opens pkg to target.module` theo phạm vi cần thiết, rồi dùng `privateLookupIn` |
| Factory muốn giảm quyền trước khi chia sẻ | Chỉ chia sẻ lookup tối thiểu hoặc các handle đã được chọn; cân nhắc `dropLookupMode` theo hợp đồng |
| Bên nhận yêu cầu một member không được phép truy cập | Trả lỗi có thông tin mục tiêu, module và loại thiếu quyền; không tự thêm các cờ mở rộng toàn hệ thống |
| Cần chuyển đổi kiểu tham số/trả về | Tạo adapter `asType`/API tương ứng **sau khi đã có handle hợp lệ** |
| Cần lựa chọn member bằng tên tại runtime | Xác định module và lookup class, tra cứu đúng chữ ký, xử lý riêng lỗi “không tìm thấy” và lỗi quyền |

**Thực tế quan trọng:** có thể truyền một `MethodHandle` đã được tìm hợp lệ đến nơi khác để gọi, ngay cả khi nơi nhận không tự có quyền dùng `Lookup` để tìm private member đó. Đây chính là lý do lookup và handle đều cần được coi là đối tượng mang năng lực thực thi trong thiết kế API.

### Không tự mở private member của thư viện chỉ vì “dùng MethodHandle”

`MethodHandles.Lookup` vẫn phải tuân thủ module encapsulation. Việc Method Handle được JDK dùng bên trong core reflection kể từ Java 18 không phải lý do để bỏ qua `opens`/`exports` hay gọi các API không được công bố.

Nếu việc truy cập sâu bị từ chối, hãy xem lại **hợp đồng giữa các module** và chọn một trong các giải pháp: public API, extension point, accessor có chủ đích hoặc package được mở với phạm vi rõ ràng.

## 9. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Nên kiểm tra |
| --- | --- | --- |
| `lookup.lookupClass()` không phải lớp mong đợi | `MethodHandles.lookup()` được gọi trong helper, factory hoặc adapter | Dòng mã nào **thực sự** gọi `lookup()`? |
| `lookupModes()` có giá trị khó hiểu | Đang đọc bitmask như một số thứ tự/quyền duy nhất | Kiểm tra bit bằng `&`; đối chiếu API của JDK hiện dùng |
| `findStatic` không tìm được method | Sai tên, sai `MethodType` hoặc dùng nhầm static/instance | `NoSuchMethodException` và chữ ký khai báo |
| `findVirtual` báo lỗi truy cập | Member/loại đích không truy cập được trong ngữ cảnh lookup | `lookupClass`, modes, lớp đích, JPMS |
| `privateLookupIn` ném `IllegalAccessException` | Caller lookup thiếu mode cần thiết, hoặc package đích chưa mở khi khác module | `PRIVATE`, `MODULE`, `opens` tới module của caller lookup |
| `publicLookup` gọi được public nhưng không lấy được private method | Lookup công khai không có năng lực private | Đổi thiết kế hoặc xin mở quyền hợp lệ từ module sở hữu |
| `Lookup.in(...)` làm mất quyền | Đổi lookup class/module có thể hạ quyền | So sánh `lookupClass()` và `lookupModes()` trước/sau |
| Handle đã tạo nhưng `invokeExact` lỗi | Kiểu tại điểm gọi không khớp `handle.type()` | Kiểu receiver, kiểu tham số, **kiểu trả về** |
| Adapter tạo được nhưng lời gọi thất bại | Giá trị runtime không chuyển đổi được hoặc method đích ném lỗi | Quy tắc `asType` và dữ liệu thực tế |
| “Hạ quyền lookup” nhưng handle cũ vẫn chạy | Hạ quyền lookup mới không thu hồi handle đã tạo | Thiết kế quyền cấp phát handle từ đầu |

### Checklist tối thiểu

~~~text
[ ] Lookup duoc tao O LOP NAO? (lookupClass)
[ ] Lookup co nhung MODE nao? (lookupModes, check bit)
[ ] Member dich thuoc lop/package/module nao?
[ ] Loai member la public, private, protected hay package-private?
[ ] Package duoc exports hay opens, va cho module nao?
[ ] Member da duoc tim va tao handle thanh cong chua?
[ ] Neu co adapter, da kiem tra lai handle.type() chua?
[ ] Neu goi handle, da xu ly loi kieu va loi method dich chua?
[ ] Da chia se lookup/handle voi pham vi thuc su can thiet chua?
~~~

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao việc một lookup có `lookupClass() == Account.class` chưa đủ để khẳng định nó gọi được tất cả private method của `Account`?

**Trả lời:** Vì phải xét cả `lookupModes()`, cách lookup được tạo và các quy tắc truy cập còn hiệu lực. Cùng lookup class có thể có các lookup modes khác nhau; kiểu member và ranh giới module vẫn quan trọng.

**Câu 2.** `MethodHandles.lookup()` nằm trong `Helper.create()`, nhưng `App.main()` gọi `Helper.create()`. `lookupClass()` sẽ đại diện cho lớp nào?

**Trả lời:** `Helper` vì `MethodHandles.lookup()` lấy lớp chứa **lời gọi thực tế**.

**Câu 3.** Một module export package chứa lớp public nhưng không opens package đó. Module khác có `Lookup` đủ quyền trong chính module của mình. Có mặc nhiên `privateLookupIn` vào private member của lớp public được không?

**Trả lời:** Không. `exports` giúp dùng public API; deep reflection xuyên module thông thường cần `opens` phù hợp cho module gọi.

**Câu 4.** `findStatic` tìm private method thất bại bằng `IllegalAccessException`. Có thể sửa bằng cách gọi `asType` với chữ ký `(Object)Object` không?

**Trả lời:** Không. `asType` chỉ là adapter **của một handle đã tồn tại** và không cấp thêm quyền. Phải giải quyết quyền truy cập khi tạo handle.

**Câu 5.** Một handle đến private method đã được tạo hợp lệ rồi chia sẻ cho module khác. Module nhận không có lookup private tương ứng. Module đó có thể sử dụng handle không?

**Trả lời:** Có thể, nếu bên nhận có handle và gọi đúng hợp đồng kiểu/giá trị. Quyền truy cập member đã được kiểm tra khi tạo handle; chính vì vậy việc chia sẻ handle cũng là trao một năng lực cần kiểm soát.

**Câu 6.** `lookupModes()` có thể dùng để so sánh `lookupA.lookupModes() > lookupB.lookupModes()` để kết luận A có nhiều quyền hơn B không?

**Trả lời:** Không. Đây là bitmask, các bit mang nghĩa khác nhau và còn phụ thuộc lookup class, module và member đích. Cần kiểm tra từng mode có liên quan và quyền thực tế với thao tác đang cần.

## Ghi nhớ

- **`Lookup` là năng lực truy cập có ngữ cảnh**, không chỉ là tiện ích tìm tên method.
- `lookupClass()` cho biết lớp đại diện cho ngữ cảnh; `lookupModes()` là **bitmask các chế độ truy cập**, nên phải kiểm tra theo bit và xem cùng quy tắc JPMS.
- `MethodHandles.lookup()` phụ thuộc **lớp gọi thực tế**; `publicLookup()` chỉ cho năng lực truy cập công khai phù hợp; `in(...)` có thể làm giảm quyền; `privateLookupIn(...)` đòi hỏi quyền và package `opens` hợp lệ khi cần truy cập sâu.
- **Kiểm tra quyền đối với member xảy ra khi tìm/tạo handle**. Những lần gọi handle sau đó vẫn phải đúng chữ ký, đúng dữ liệu và xử lý lỗi của thao tác đích.
- Adapter thay đổi cách gọi một handle hợp lệ, **không cấp quyền vượt qua đóng gói module**.
- Chia sẻ `Lookup` hoặc `MethodHandle` đồng nghĩa chia sẻ khả năng tìm/gọi member trong phạm vi tương ứng. Hãy cấp quyền ở mức tối thiểu theo thiết kế.

**Tài liệu đối chiếu:** Javadoc `java.lang.invoke.MethodHandles` và `MethodHandles.Lookup` (các mục `lookup`, `publicLookup`, `lookupClass`, `lookupModes`, `in`, `privateLookupIn`, `findStatic`, `findVirtual`); Javadoc `java.lang.invoke.MethodHandle`; quy tắc module `exports` và `opens` trên phiên bản JDK đang sử dụng. JEP 416: [Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416).
