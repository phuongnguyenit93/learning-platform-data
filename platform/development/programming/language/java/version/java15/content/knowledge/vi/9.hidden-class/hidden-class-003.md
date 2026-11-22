# Khả năng sử dụng đối tượng hidden class qua kiểu công khai (Java 15+)

## 1. Vấn đề: lớp bị ẩn, đối tượng vẫn có thể được sử dụng

**Hidden class** là một lớp được Java Virtual Machine định nghĩa động, thường qua `MethodHandles.Lookup.defineHiddenClass(...)`. Tính năng này được đưa vào Java 15 và tiếp tục được hỗ trợ trong các JDK hiện hành. Hidden class dành cho những tình huống framework hoặc thư viện sinh lớp triển khai lúc chạy mà **không muốn lớp triển khai trở thành một tên lớp thông thường mà mã khác có thể liên kết trực tiếp**.

Điểm quan trọng của bài học: **đối tượng của hidden class vẫn là một đối tượng Java bình thường về mặt kiểu và hành vi**. Nếu hidden class `implements` một **interface công khai** hoặc `extends` một **lớp cha công khai** phù hợp, mã bên ngoài có thể nhận đối tượng qua kiểu đó, gọi những phương thức được khai báo trong hợp đồng công khai, lưu trong biến/collection và truyền qua các API nhận kiểu công khai.

Tính chất *hidden* ảnh hưởng đến **việc đặt tên và liên kết tới chính lớp triển khai**, không tự cấm việc dùng đối tượng thông qua một kiểu cha mà người gọi có thể nhìn thấy.

Ví dụ về ý tưởng:

```java
// Đây là minh họa trong phương thức, không phải chương trình độc lập.
Greeting service = GreetingFactory.create();
String message = service.greet("Linh");
```

`Greeting` là interface công khai, `GreetingFactory.create()` là phương thức công khai trả về interface đó. Người gọi **không cần biết, đặt tên hay nhập (import)** tên hidden class triển khai.

## 2. Phân biệt kiểu tĩnh và lớp lúc chạy

Một biến đối tượng có thể được nhìn ở hai tầng:

- **Kiểu tĩnh (compile-time type)**: kiểu Java mà mã nguồn công khai có thể khai báo, ví dụ `Greeting`, `Runnable`, `Callable<String>`, một abstract superclass công khai hoặc `Object`. Trình biên dịch dựa vào kiểu này để kiểm tra các lời gọi.
- **Lớp thực lúc chạy (runtime class)**: lớp cụ thể mà `object.getClass()` trả về. Đây có thể là một hidden class; `object.getClass().isHidden()` trả `true`.

Giả sử một hidden class thực thi `Greeting`:

```java
Greeting greeting = GreetingFactory.create();
boolean ok = greeting instanceof Greeting;
boolean hidden = greeting.getClass().isHidden();
```

Cả `ok` và `hidden` đều có thể bằng `true` đồng thời. Không có mâu thuẫn: **lớp triển khai bị ẩn tên**, còn **quan hệ implements interface vẫn là quan hệ kiểu thật** do JVM kiểm tra.

Khi viết `greeting.greet("Linh")`, bytecode của người gọi liên kết tới phương thức trên `Greeting` công khai. Lúc chạy, JVM dispatch tới phương thức của đối tượng triển khai. Cơ chế gọi phương thức thông qua interface hoặc lớp cha vẫn hoạt động.

Ngược lại, khi `Greeting` chỉ khai báo `greet`, người gọi không thể viết `greeting.onlyInImplementation()` chỉ vì hidden class có phương thức đó: **kiểu tĩnh công khai không công bố phương thức này**. Muốn hỗ trợ công khai, hãy đưa hành vi vào interface/lớp cha thích hợp hoặc qua một API công khai khác.

## 3. Điều kiện để một public contract thực sự sử dụng được

Cần phân biệt **lớp triển khai** và **hợp đồng được công bố**:

1. Interface hoặc superclass phải là **kiểu bình thường, có thể liên kết bằng tên**, và phải có phạm vi truy cập phù hợp (ví dụ `public interface Greeting` trong một package mà ứng dụng khách đọc được).
2. Hidden class có thể `implements Greeting` hoặc `extends` một superclass công khai, miễn bytecode hợp lệ và quan hệ kế thừa đúng theo JVM.
3. Factory hoặc API trao đối tượng phải có chữ ký sử dụng **kiểu công khai**, ví dụ `public static Greeting create()`; không thể viết tên hidden class trực tiếp trong chữ ký Java công khai cho caller liên kết.
4. Phương thức mà client muốn gọi phải nằm trong hợp đồng mà kiểu tĩnh cho phép truy cập. `public` của phương thức trên một hidden class **không tự làm tên lớp hidden trở thành có thể liên kết**.
5. Cùng một `Greeting` phải được nhận diện qua cơ chế nạp lớp tương thích. Việc một interface ở cùng tên nhưng bị nạp bằng các class loader khác nhau có thể làm `ClassCastException` khi cast.

Sơ đồ quan hệ:

```text
Client (package lesson.client)
  |
  | biên dịch với Greeting + GreetingFactory
  v
public interface Greeting <------ implements ------ hidden runtime class
  ^                                            |
  |                                            | object instance
  +-------- factory trả về Greeting <-----------+
```

Người gọi chỉ liên kết tới **`Greeting` và `GreetingFactory`**. Khả năng khám phá tên hidden class không tham gia vào hợp đồng gọi `greet`.

## 4. Ví dụ hoàn chỉnh: client ở package khác vẫn gọi được

Ví dụ sau dùng các API được hỗ trợ từ Java 15, biên dịch theo Java 17 để có thể chạy bằng JDK 17+. Nó minh họa tách **public interface**, **lớp triển khai sẽ trở thành hidden class**, **public factory**, và **client ở package khác**.

Cấu trúc tệp:

```text
lesson/
  api/
    Greeting.java
    HiddenGreeting.java
    GreetingFactory.java
  client/
    Client.java
```

### 4.1. Public interface: `lesson/api/Greeting.java`

```java
package lesson.api;

public interface Greeting {
    String greet(String name);
}
```

Đây là **kiểu công khai** để người dùng thư viện khai báo biến, viết tham số, giá trị trả về hoặc collection. Nó không phụ thuộc vào tên triển khai `HiddenGreeting`.

### 4.2. Bytecode triển khai: `lesson/api/HiddenGreeting.java`

```java
package lesson.api;

final class HiddenGreeting implements Greeting {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Tệp này chỉ phục vụ **biên dịch ví dụ để lấy bytecode**. Bản chất hidden class không đến từ từ khóa `final`, `public` hay việc khai báo package-private trong source; lớp sẽ trở thành hidden class **khi bytecode được đưa qua `defineHiddenClass`**. Đoạn mã trên tự nó là lớp Java thông thường nếu được nạp theo cách thông thường.

### 4.3. Public factory: `lesson/api/GreetingFactory.java`

```java
package lesson.api;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class GreetingFactory {
    private GreetingFactory() {}

    public static Greeting create() throws Throwable {
        byte[] bytes;
        try (InputStream input = GreetingFactory.class.getResourceAsStream("HiddenGreeting.bytes")) {
            if (input == null) {
                throw new IOException("Missing HiddenGreeting.bytes");
            }
            bytes = input.readAllBytes();
        }
        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(bytes, true);
        Class<?> hiddenType = hiddenLookup.lookupClass();
        MethodHandle constructor =
                hiddenLookup.findConstructor(hiddenType, MethodType.methodType(void.class));
        return (Greeting) constructor.invoke();
    }
}
```

Giải thích từng bước:

1. `getResourceAsStream("HiddenGreeting.bytes")` đọc tài nguyên bytecode trong **package `lesson.api`**. Tên `.bytes` chỉ là tên tài nguyên của ví dụ, không phải định dạng classfile đặc biệt; nội dung vẫn là bytecode `.class` hợp lệ.
2. `MethodHandles.lookup()` tạo một `Lookup` gắn với `GreetingFactory` trong cùng package. `defineHiddenClass(bytes, true)` định nghĩa **lớp hidden**; tham số `true` yêu cầu khởi tạo lớp khi định nghĩa. API trả về một `Lookup` mà `lookupClass()` là hidden class vừa tạo.
3. `findConstructor` lấy method handle cho constructor không tham số của hidden class. Gọi `constructor.invoke()` sinh đối tượng.
4. `(Greeting)` là ép kiểu dựa trên quan hệ **implements** thật; factory trả object dưới **kiểu công khai**.

Ví dụ dùng `throws Throwable` để giữ tập trung vào cơ chế nạp và khởi tạo lớp. Một factory sản xuất nên có hợp đồng ngoại lệ gọn hơn, xử lý rõ lỗi tài nguyên/bytecode, không phát tán mọi `Throwable` tới API người dùng.

`defineHiddenClass` có yêu cầu về quyền của `Lookup` và package: lookup phải có **full privilege access** và classfile đầu vào phải thuộc **cùng package** với lookup class. Không thể tùy tiện dùng `publicLookup()` để định nghĩa hidden class ở mọi package hay vượt ranh giới module.

### 4.4. Client ở package khác: `lesson/client/Client.java`

```java
package lesson.client;

import lesson.api.Greeting;
import lesson.api.GreetingFactory;

public class Client {
    public static void main(String[] args) throws Throwable {
        Greeting greeting = GreetingFactory.create();
        System.out.println("message=" + greeting.greet("Linh"));
        System.out.println("hidden=" + greeting.getClass().isHidden());
        System.out.println("public-type=" + (greeting instanceof Greeting));
        System.out.println("assignable=" + Greeting.class.isAssignableFrom(greeting.getClass()));
        try {
            Class.forName(greeting.getClass().getName());
            System.out.println("by-name=found");
        } catch (ClassNotFoundException exception) {
            System.out.println("by-name=not-found");
        }
    }
}
```

Client chỉ import `lesson.api.Greeting` và `lesson.api.GreetingFactory`. Client **không import hidden class**, không cần biết tên classfile trước khi định nghĩa, và vẫn gọi được `greet` bình thường.

### 4.5. Biên dịch, đưa bytecode thành resource, chạy

Chạy từ thư mục chứa thư mục con `lesson`. Trên macOS/Linux:

```bash
javac --release 17 -encoding UTF-8 \
  lesson/api/Greeting.java \
  lesson/api/HiddenGreeting.java \
  lesson/api/GreetingFactory.java \
  lesson/client/Client.java

mv lesson/api/HiddenGreeting.class lesson/api/HiddenGreeting.bytes

java -cp . lesson.client.Client
```

Với PowerShell trên Windows, lệnh tương ứng:

```powershell
javac --release 17 -encoding UTF-8 lesson/api/Greeting.java lesson/api/HiddenGreeting.java lesson/api/GreetingFactory.java lesson/client/Client.java
Rename-Item lesson/api/HiddenGreeting.class HiddenGreeting.bytes
java -cp . lesson.client.Client
```

Bước đổi tên **chỉ đổi tên tệp chứa bytecode**. Nó không đổi tên lớp trong constant pool và không tự tạo hidden class. Lệnh `defineHiddenClass` ở **runtime** mới thực sự tạo lớp hidden. Bằng cách đổi `.class` thành `.bytes`, ta tránh để ordinary class `lesson.api.HiddenGreeting` vô tình được nạp theo tên từ classpath trong ví dụ. Khi đóng gói JAR, hãy đóng gói `HiddenGreeting.bytes` như một resource cùng package với factory.

**Stdout chính xác:**

```text
message=Xin chào, Linh!
hidden=true
public-type=true
assignable=true
by-name=not-found
```

Điều được chứng minh:

- `message=...`: client thực sự gọi phương thức công khai được hidden class triển khai.
- `hidden=true`: lớp runtime của object là hidden class.
- `public-type=true` và `assignable=true`: quan hệ kiểu công khai được JVM nhận diện.
- `by-name=not-found`: gọi `Class.forName` bằng tên mà `getClass().getName()` trả về **không tìm ra hidden class**.

Tên runtime của hidden class thường chứa phần định danh đặc biệt không ổn định; ví dụ cố ý **không in nguyên tên** để stdout tái lập trên các lần chạy/JDK.

## 5. Vì sao không tìm được hidden class theo tên nhưng vẫn gọi được?

Hidden class **không có binary name thông thường** để các class khác ghi tham chiếu tới trong constant pool. Vì thế:

- Không thể dựa vào `Class.forName(hiddenClass.getName())` hay `ClassLoader.loadClass(hiddenClass.getName())` để tra ra chính hidden class đã được định nghĩa.
- Client không thể có biểu thức `new HiddenRuntimeName()`, `HiddenRuntimeName.class`, hay viết tên hidden class thật trong chữ ký nguồn Java ở các class bình thường.
- Tuy vậy, khi factory đưa **đối tượng đã được tạo** cho client dưới dạng `Greeting`, JVM không cần tra tên hidden class của đối tượng: nó đã có reference tới đối tượng và biết kiểu runtime.
- Client vẫn có thể gọi `getClass()`, `isHidden()`, `isAssignableFrom(...)` hoặc API reflection phù hợp khi đã có `Class<?>/Object`, **tuân theo các kiểm tra truy cập**. *Không tìm được theo tên* không có nghĩa là *mọi thao tác reflection đều bị cấm*.

Ví dụ `Greeting.class.isAssignableFrom(greeting.getClass())` trả `true`, dù `Class.forName(greeting.getClass().getName())` thất bại.

Một lớp thường cũng có thể tên `HiddenGreeting` nếu bạn giữ tệp `.class` trên classpath; điều đó tạo ra **một lớp thường riêng biệt**, không làm lộ tên hay thay thế hidden class đã được định nghĩa. Demo đổi tên resource để tránh hiểu sai khi thử nghiệm.

## 6. Những kiểu công khai có thể dùng làm cửa giao tiếp

| Kiểu client nhìn thấy | Có thể dùng object hidden class? | Giới hạn quan trọng |
|---|---|---|
| **`public interface`** được hidden class `implements` | **Có**: gán biến, gọi method của interface, `instanceof`, cast | Interface phải truy cập được; phương thức riêng của implementation không tự hiện ra |
| **`public abstract class` / superclass** được hidden class `extends` | **Có**: gọi method public/protected theo quy tắc Java, dùng polymorphism | Phải thỏa quy tắc kế thừa, constructor, `final`, module và mức truy cập |
| **`java.lang.Object`** | **Có**: mọi object đều có thể gán vào `Object` | Mất API nghiệp vụ; muốn gọi method đặc thù cần kiểu chung khác hoặc cơ chế động |
| **`List<Greeting>`, `Optional<Greeting>`** | **Có**: container nắm giữ tham chiếu kiểu interface | Không biến hidden class thành kiểu có thể đặt tên; generic vẫn dựa vào kiểu công khai |
| **Method handle / reflection** nhận qua factory nội bộ | **Có thể** gọi member khi có quyền và handle/metadata phù hợp | Cần thiết kế quyền và lỗi cẩn thận; không phù hợp làm public contract mặc định |

Ví dụ một dịch vụ trả collection:

```java
// Minh họa trong một phương thức có Greeting greeting.
java.util.List<Greeting> items = java.util.List.of(greeting);
String text = items.get(0).greet("Linh");
```

Việc lưu vào `List<Greeting>` vẫn hợp lệ vì mỗi phần tử triển khai `Greeting`. Một factory có thể thay thế nhiều phiên bản hidden implementation trong tương lai **mà không cần đổi chữ ký public API** nếu hợp đồng `Greeting` được giữ ổn định.

Với superclass, quy tắc cũng tương tự. Chẳng hạn `public abstract class Task { public abstract String run(); }` có thể là lớp cha được công khai; một hidden class extends `Task` và override `run()` có thể được trả về với kiểu `Task`. Đây là **minh họa cú pháp**, không phải chương trình độc lập; khi thiết kế thật còn phải đảm bảo constructor và module/package phù hợp.

## 7. Phân biệt “công khai” ở từng mức

**`public interface` không tự mở quyền truy cập mọi thứ trong hidden class.** Java có nhiều lớp kiểm tra khác nhau:

- **Truy cập tới public API**: client thấy `Greeting` nếu package và module cho phép; trên Java Platform Module System, package chứa public API cần được `exports` tới module client khi dùng named modules.
- **Truy cập tới implementation**: lớp hidden vẫn có các member với quyền `private`, package-private, `protected`, `public` như bytecode định nghĩa; reflection hoặc method handle vẫn phải tuân thủ access checks.
- **Quyền để định nghĩa hidden class**: `Lookup.defineHiddenClass` cần lookup có **full privilege access**; bytecode phải thuộc cùng package với lookup class. Nếu phải đi qua module/package khác, việc lấy lookup đủ quyền có các điều kiện module readability/openness riêng; không có cơ chế bỏ qua kiểm soát quyền tự động.
- **Quan hệ nestmate**: nếu bài toán thực sự cần hidden class là nestmate của lookup class, có thể dùng `Lookup.ClassOption.NESTMATE`; tùy chọn này ảnh hưởng quyền truy cập private giữa thành viên cùng nest, **không cần** cho việc implements một public interface trong ví dụ.
- **Độ bền của lớp**: theo mặc định hidden class không có quan hệ mạnh với defining class loader như lớp bình thường; JVM có thể unload khi lớp không còn được giữ sống. Tùy chọn `Lookup.ClassOption.STRONG` thay đổi quan hệ này. Đây là cân nhắc vòng đời và tài nguyên, không quyết định khả năng cast sang `Greeting`.

Vì vậy, nhận object qua public interface **không** có nghĩa là mọi phương thức private của hidden implementation trở thành public. Ngược lại, việc lớp hidden không thể tìm theo tên **không** phải một ranh giới bảo mật/sandbox: bytecode resource vẫn có thể tồn tại trong JAR và Java access control vẫn là cơ chế quản trị quyền thực sự.

## 8. Khi thiết kế API thực tế nên làm gì?

### 8.1. Giữ chữ ký public ổn định

Phương thức factory nên công bố `Greeting`, `Task`, `Function<T,R>` hoặc một kiểu công khai thích hợp:

```java
public static Greeting create() throws Throwable
```

Đây là chữ ký *trong ví dụ*, nơi `Throwable` giúp trình diễn trực tiếp `MethodHandle.invoke()`. API sản xuất nên xử lý lỗi ở ranh giới factory và công bố những exception có ý nghĩa với caller; tránh buộc mọi client phải xử lý `Throwable` chung chung.

Không thiết kế API yêu cầu client biết hidden class thực, kiểm tra tên runtime chính xác, gọi constructor của implementation trực tiếp, hoặc định danh implementation qua một tên lớp có thể nạp lại.

### 8.2. Đừng dùng tên lớp hidden làm ID lâu dài

Vì tên runtime của hidden class không phải binary name ổn định, tránh ghi nó thành key trong cấu hình nghiệp vụ, registry bền vững, giao thức trao đổi hoặc format tuần tự hóa phụ thuộc tên triển khai.

Nếu cần một danh tính ổn định, dùng **ID công khai riêng** hoặc cấu trúc dữ liệu (DTO) do ứng dụng định nghĩa. Việc một đối tượng `implements Greeting` không tự khiến nó có thể serialize theo format bất kỳ; chính sách serialize phụ thuộc API và type cụ thể.

### 8.3. Không giả định mọi hệ thống khám phá plugin sẽ tìm được implementation

Cơ chế dựa vào **tên class** như `Class.forName`, quét classpath theo binary name hoặc metadata đăng ký class thông thường sẽ không tự phát hiện được hidden runtime class đã định nghĩa. Muốn cung cấp hành vi như plugin, hãy đăng ký **public factory**, **public provider**, hoặc **đối tượng interface đã tạo** bằng registry rõ ràng.

Hidden class đặc biệt phù hợp với các khuôn mẫu framework như tạo implementation runtime để ẩn chi tiết sinh mã; ứng dụng Java bình thường không cần ép mọi lớp thành hidden class nếu lớp Java thông thường đáp ứng tốt hợp đồng.

## 9. Lỗi thường gặp khi thử nghiệm

| Biểu hiện | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `Class.forName(hiddenType.getName())` báo `ClassNotFoundException` | Hidden class không có binary name có thể nạp theo tên | Đây là hành vi đúng; trao đối tượng qua interface hoặc giữ `Class<?>`/`Lookup` nếu cần thao tác nội bộ |
| `greeting instanceof Greeting` trả `false`, hoặc cast lỗi | Hidden implementation không thực thi đúng interface, hoặc interface được nạp bằng class loader không tương thích | Kiểm tra bytecode, cùng identity của `Greeting` và đường nạp lớp |
| `IllegalAccessException` khi `defineHiddenClass` | Lookup không đủ quyền hoặc sai phạm vi package/module | Tạo `Lookup` từ lớp có đủ quyền trong package đích; không dùng `publicLookup()` để thay cho full privilege |
| `IllegalArgumentException` ở bước định nghĩa | Classfile không hợp lệ cho ngữ cảnh, ví dụ không cùng package với lookup class | Kiểm tra package thực của classfile, lookup class và yêu cầu API |
| `NoClassDefFoundError` hoặc lỗi linkage | Bytecode tham chiếu một kiểu không thể resolve/khác class loader | Giữ các interface/phụ thuộc bình thường truy cập được trong loader/module liên quan |
| Không thấy `HiddenGreeting.bytes` | Resource chưa đặt đúng package trong classpath/JAR | Đọc resource cùng package với factory, kiểm tra quy trình build/packaging |
| Cố gọi method chỉ có trong implementation qua `Greeting` | Interface không khai báo method đó | Bổ sung hợp đồng public đúng nhu cầu hoặc dùng API khác |
| Hai hidden instance có vẻ giống nhau nhưng `getClass()` khác | Mỗi lần `defineHiddenClass` tạo một định nghĩa lớp mới | Không dùng `==` của runtime class để suy ra cùng chức năng; quản lý identity theo API của ứng dụng |
| Chạy được `Class.forName("lesson.api.HiddenGreeting")` sau khi biên dịch | Tệp `HiddenGreeting.class` bình thường vẫn tồn tại trong classpath | Phân biệt lớp thường với hidden class đã tạo; trong demo hãy đổi resource sang `.bytes` như hướng dẫn |
| Nhầm `NESTMATE` với quyền truy cập interface | Nestmate liên quan quyền private giữa các lớp cùng nest | Public interface chỉ cần quan hệ implements và khả năng truy cập hợp lệ |

Lỗi do package, access hoặc linkage cần được báo và xử lý theo loại lỗi thực tế. Không nên bắt tất cả rồi âm thầm trả `null` vì caller sau đó khó biết nguyên nhân.

## 10. Kiểm thử hợp đồng công khai

Một kiểm thử đáng tin của API dùng hidden class nên kiểm chứng **kết quả hành vi**, không cố gán tên lớp triển khai. Tập trường hợp tối thiểu:

1. Factory trả về **không null** và là instance của interface công khai.
2. Mọi hành vi được công bố trên interface có kết quả đúng với dữ liệu thử, ví dụ `greet("Linh")`.
3. `object.getClass().isHidden()` là `true` nếu đúng là API **có yêu cầu cụ thể** phải sinh hidden class.
4. `Interface.class.isAssignableFrom(object.getClass())` trả `true`.
5. Không có chỗ nào ở client cần import/tạo object qua tên implementation.
6. Kiểm tra đường phát hành resource `.bytes` trong JAR và cách factory báo lỗi khi bytecode bị thiếu.
7. Nếu định nghĩa nhiều lớp động, đo vòng đời tài nguyên, khả năng giữ references và quản lý unload; không khẳng định JVM sẽ garbage collect ở một thời điểm xác định.

Kiểm thử bên ngoài package API có giá trị hơn vì giúp lộ lỗi vô tình phụ thuộc vào package-private implementation. Ví dụ ở mục 4 đặt client trong `lesson.client`, do đó việc gọi `greet` chứng minh hợp đồng public có thể sử dụng xuyên package.

## 11. Kết luận

Hidden class trong Java 15+ có thể **không được gọi bằng tên binary** nhưng vẫn **tạo instance, thực hiện polymorphism, cast và gọi qua kiểu công khai**. Cách thiết kế thường thấy là: framework định nghĩa hidden implementation bằng `MethodHandles.Lookup.defineHiddenClass`, tạo instance nội bộ, rồi trả về một interface hoặc lớp cha công khai. Client chỉ phụ thuộc vào contract và không cần biết lớp triển khai được sinh thế nào.

Để giữ API bền vững, hãy tách rõ ba phần: **public contract ổn định**, **cơ chế định nghĩa hidden class nằm trong thư viện/framework**, và **đối tượng được trao cho client qua public type**. Kiểm tra quyền `Lookup`, class loader, module và vòng đời ở tầng định nghĩa, đồng thời kiểm thử hành vi qua interface ở tầng người dùng.

**Tài liệu chính thức hiện hành:**

- [Java SE 26 — `MethodHandles.Lookup` (`defineHiddenClass`)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 26 — `Class` (`isHidden`, hidden class)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html)
- [Java SE 26 — `MethodHandles.Lookup.ClassOption` (`NESTMATE`, `STRONG`)](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html)
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371) (thiết kế tính năng được đưa vào Java 15; vẫn là cơ sở cho API hiện hành).
