# Java Reflection và JPMS: điều kiện truy cập khi caller và lớp đích ở cùng module

Trong Java 9+ (bao gồm Java 17, 21), **JPMS — Java Platform Module System** đặt thêm ranh giới giữa các module. Tuy vậy, khi lớp **thực sự thực hiện Reflection** (*caller*) và lớp **khai báo thành viên cần truy cập** cùng nằm trong **một module**, việc kiểm tra và mở quyền Reflection có quy tắc thuận lợi hơn so với tình huống đi qua ranh giới module. Điều quan trọng là không đánh đồng *cùng module* với *được quyền truy cập trực tiếp mọi thành viên `private`*.

Kết luận cốt lõi:

- **Tra cứu metadata** qua `getDeclaredField()`, `getDeclaredMethod()`, `getDeclaredConstructor()` là bước tìm thành viên; tìm thấy thành viên `private` không có nghĩa là đọc/gọi được ngay.
- **Truy cập Java thông thường** vẫn tuân theo `public`, `protected`, package-private và `private`. Hai lớp khác nhau nhưng ở cùng module không tự động được xem là cùng package hoặc cùng nest.
- Với Reflection, nếu **caller và lớp khai báo thành viên ở cùng module**, `AccessibleObject#trySetAccessible()` có thể bật chế độ bỏ qua kiểm tra truy cập Java cho thành viên đó; `setAccessible(true)` cũng được phép theo điều kiện *same module* của JPMS. Việc sử dụng các thao tác sau khi bật quyền vẫn phải tuân theo những giới hạn riêng, như giới hạn sửa `final`.
- Không cần khai báo `exports` hoặc `opens` **chỉ để phục vụ truy cập nội bộ cùng module**. Hai chỉ thị này chủ yếu điều khiển việc package được sử dụng từ **module khác**.

Bài này làm rõ phạm vi "same module", hai tầng kiểm tra truy cập, cách xác minh bằng mã Java có `module-info.java`, và các trường hợp dễ sai khi xây công cụ Reflection.

## 1. "Caller" và "cùng module" chính xác là gì?

Một module là đơn vị đóng gói các package. Named module được khai báo bằng `module-info.java`; còn mã trên classpath thường thuộc **unnamed module** gắn với class loader.

Trong ngữ cảnh Reflection:

- **Target/declarer** là lớp hoặc interface thực sự **khai báo** field, method hoặc constructor cần thao tác; xem `member.getDeclaringClass()`.
- **Caller** là lớp có mã **thực sự gọi** API kiểm tra/mở quyền Reflection, chẳng hạn `trySetAccessible()`. Không nên mặc định caller là lớp khởi đầu một yêu cầu ở tầng ứng dụng.
- Muốn kiểm tra hai lớp có đúng là **cùng một đối tượng module**, so sánh `Class#getModule()` bằng `==`.

Ví dụ:

~~~java
boolean sameModule = Caller.class.getModule()
        == Target.class.getModule();
~~~

Đoạn trên là **mã minh họa**, với `Caller` và `Target` là hai lớp đã định nghĩa ở ứng dụng. So sánh module theo **danh tính** tốt hơn so sánh chuỗi từ `Module#getName()`: unnamed module có tên `null`; đồng thời cùng một tên module không đủ chứng minh hai lớp thuộc cùng một đối tượng module ở các môi trường class loader/layer khác nhau.

**Đối với unnamed module:** đừng kết luận mọi lớp trên mọi class loader đều ở cùng một unnamed module. Mỗi class loader có unnamed module của nó. Vì vậy hãy kiểm tra đối tượng `Module` thực tế khi lớp được tải động hoặc ứng dụng có nhiều class loader.

## 2. Phân biệt ba câu hỏi về quyền truy cập

Có ba câu hỏi độc lập:

| Câu hỏi | API hoặc quy tắc liên quan | Khi hai lớp cùng module |
| --- | --- | --- |
| **Có tìm thấy metadata của thành viên không?** | `Class#getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor` | Có thể tìm cả thành viên `private` khai báo trực tiếp, nếu tên/chữ ký đúng |
| **Có sử dụng được thành viên theo kiểm tra truy cập hiện tại không?** | Quy tắc Java `public`/`protected`/package-private/`private`, `canAccess(receiver)` | Vẫn phải thỏa quyền thông thường, trừ khi đã bật bỏ qua kiểm tra |
| **Có được bật bỏ qua kiểm tra truy cập Java bằng Reflection không?** | `trySetAccessible()`, `setAccessible(true)` | Điều kiện *declaring class cùng module với caller* cho phép bật quyền; không cần package `opens` |

Ví dụ: `app.Main` và `model.Vault` có thể cùng module, nhưng ở **hai package khác nhau**. Nếu `Vault` có field `private String token`, `Vault.class.getDeclaredField("token")` vẫn trả về `Field`. Tuy nhiên `field.canAccess(vault)` thường trả `false` trước khi bật quyền vì `Main` không phải lớp/nest được phép truy cập `private` của `Vault`. Sau khi `field.trySetAccessible()` thành công, `field.get(vault)` có thể đọc giá trị.

### Quy tắc Java thông thường vẫn giữ nguyên

- `public`: cần chú ý mức truy cập của **cả lớp khai báo lẫn thành viên**; việc package không `exports` không cấm mã trong **cùng module** truy cập các khai báo `public` hợp lệ.
- `protected`: được phép theo quy tắc cùng package hoặc quan hệ kế thừa, với các điều kiện bổ sung đối với truy cập ngoài package. Chỉ "cùng module" là chưa đủ.
- Package-private (không ghi modifier): hai lớp ở **khác package** không được tự động truy cập, cho dù thuộc cùng module.
- `private`: tuân theo quy tắc lớp/nest của Java. Hai lớp top-level không cùng nest không có quyền truy cập trực tiếp `private` của nhau chỉ vì ở cùng module.

**Cùng module không có nghĩa là cùng package** và cũng không biến một thao tác truy cập `private` trong mã nguồn thành hợp lệ. Khi thật sự cần thao tác sâu qua Reflection, quyền mở truy cập là một **bước rõ ràng**.

## 3. Named module nội bộ: không cần `exports` và `opens`

Giả sử một dự án có cấu trúc:

~~~text
src/
└── demo.same/
    ├── module-info.java
    └── lesson/
        ├── app/
        │   └── Main.java
        └── domain/
            └── Vault.java
~~~

Tất cả các file `.java` thuộc **cùng named module** `demo.same`, dù phân thành hai package `lesson.app` và `lesson.domain`.

Nội dung `src/demo.same/module-info.java`:

~~~java
module demo.same {
}
~~~

Module này **không khai báo** `exports lesson.domain;` hoặc `opens lesson.domain;`. Đối với mã nằm trong `demo.same`, điều đó không ngăn truy cập Java `public` hợp lệ từ package khác cùng module, cũng không ngăn mở quyền sâu bằng Reflection khi đáp ứng điều kiện *same module*.

### Lớp đích `Vault`

Tệp **`src/demo.same/lesson/domain/Vault.java`**:

~~~java
package lesson.domain;

public final class Vault {
    private String token;

    private Vault(String token) {
        this.token = token;
    }

    public static Vault create() {
        return new Vault("initial");
    }

    public String status() {
        return "ready";
    }

    private String reveal(String prefix) {
        return prefix + token;
    }
}
~~~

Ở đây `Vault` là lớp `public` để `lesson.app.Main` có thể dùng trực tiếp từ **package khác cùng module**. Nhưng constructor `Vault(String)`, field `token` và method `reveal(String)` là `private`; `Main` không thể gọi/đọc trực tiếp những thành viên đó bằng cú pháp Java thông thường.

### Caller thực hiện Reflection

Tệp **`src/demo.same/lesson/app/Main.java`**:

~~~java
package lesson.app;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import lesson.domain.Vault;

public class Main {
    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println("Same module: "
                + (Main.class.getModule() == Vault.class.getModule()));
        Vault vault = Vault.create();
        System.out.println("Public access: " + vault.status());

        Field token = Vault.class.getDeclaredField("token");
        System.out.println("Field before: " + token.canAccess(vault));
        System.out.println("Field override: " + token.trySetAccessible());
        System.out.println("Field after: " + token.canAccess(vault));
        System.out.println("Field value: " + token.get(vault));

        Method reveal = Vault.class.getDeclaredMethod("reveal", String.class);
        System.out.println("Method override: " + reveal.trySetAccessible());
        System.out.println("Result: " + reveal.invoke(vault, "value="));

        Constructor<Vault> ctor = Vault.class.getDeclaredConstructor(String.class);
        System.out.println("Constructor before: " + ctor.canAccess(null));
        System.out.println("Constructor override: " + ctor.trySetAccessible());
        Vault created = ctor.newInstance("custom");
        System.out.println("Constructed: " + reveal.invoke(created, "value="));
    }
}
~~~

Chạy từ thư mục dự án bằng **JDK 17+**:

~~~bash
javac --module-source-path src -d out -m demo.same
java --module-path out --module demo.same/lesson.app.Main
~~~

**Stdout đã kiểm chứng:**

~~~text
Same module: true
Public access: ready
Field before: false
Field override: true
Field after: true
Field value: initial
Method override: true
Result: value=initial
Constructor before: false
Constructor override: true
Constructed: value=custom
~~~

### Đọc kết quả từng bước

1. So sánh `Main.class.getModule() == Vault.class.getModule()` trả `true`: đây là một named module duy nhất; không suy đoán dựa trên tên package.
2. `Vault.create()` và `vault.status()` là API `public`, có thể gọi trực tiếp từ `lesson.app` dù `module-info.java` không có `exports`. Hai package nằm nội bộ cùng module.
3. `getDeclaredField("token")` tìm thấy metadata field `private`. `token.canAccess(vault)` trả `false` với caller là `Main` vì truy cập Java thông thường không cho đọc `private` đó.
4. `token.trySetAccessible()` trả `true` vì lớp gọi và lớp khai báo ở cùng module. Sau đó `canAccess` là `true` và `get(vault)` trả `"initial"`.
5. `getDeclaredMethod("reveal", String.class)` tra đúng private method. Sau khi bật quyền, `invoke(vault, "value=")` trả `"value=initial"`.
6. `getDeclaredConstructor(String.class)` tra đúng private constructor. `ctor.canAccess(null)` ban đầu `false`; bật quyền xong, `newInstance("custom")` tạo một đối tượng mới.
7. `reveal.invoke(created, "value=")` trả `"value=custom"`, chứng minh đối tượng tạo qua constructor này có state riêng.

Cả ba trường hợp `Field`, `Method`, `Constructor` đều **tra cứu được trước**, sau đó mới bật quyền và dùng đối tượng Reflection. Ví dụ dùng `trySetAccessible()` rõ ràng để không che khuất bước kiểm tra.

## 4. Vì sao `exports`/`opens` không cần trong ví dụ trên?

JPMS dùng hai chỉ thị có mục đích khác nhau:

| Chỉ thị `module-info.java` | Mục đích điển hình | Có bắt buộc cho caller cùng module không? |
| --- | --- | --- |
| `exports lesson.domain;` | Cho module khác dùng API `public` của package qua truy cập Java thông thường | **Không** |
| `opens lesson.domain;` | Cho module khác truy cập sâu qua Reflection vào các thành viên nếu các điều kiện khác phù hợp | **Không** |
| `opens lesson.domain to some.framework;` | Chỉ định module ngoài nào có quyền deep reflection vào package đó | **Không** |
| Không khai báo hai chỉ thị | Package bị đóng đối với module ngoài theo những ranh giới tương ứng | Mã **cùng module** vẫn theo các quy tắc trong bài |

Điều kiện cùng module là một nhánh cấp phép độc lập trong tài liệu của `AccessibleObject#setAccessible` và `trySetAccessible`. Một framework ở **module khác** không tự hưởng quyền này chỉ vì nó nhận đối tượng `Class` hoặc `Field` do mã trong module đích chuyển qua.

**Không nên thêm `opens` cho cả module** chỉ để cho mã nội bộ truy cập Reflection. Việc mở package là quyết định kiến trúc có tác động tới các module khác và không cần thiết trong ví dụ *same module*.

## 5. `canAccess`, `trySetAccessible` và `setAccessible`

Cả `Field`, `Method` và `Constructor` đều kế thừa từ `AccessibleObject`.

### `canAccess(Object obj)`

Kiểm tra liệu thành viên có được truy cập theo trạng thái hiện tại với caller đang gọi hay không. Đối số `obj` phải đúng loại:

- Field hoặc method **instance**: truyền instance chứa thành viên, ví dụ `field.canAccess(vault)`.
- Field hoặc method **static**: truyền `null`.
- Constructor: truyền `null`, ví dụ `ctor.canAccess(null)`.

Đối số không hợp lệ có thể gây `IllegalArgumentException`; không dùng `canAccess(null)` cho instance field/method chỉ để hỏi "có quyền không".

### `trySetAccessible()`

Thử bật khả năng bỏ qua kiểm tra truy cập Java của đối tượng Reflection. Khi caller và declaring class **cùng module**, điều kiện same-module của JPMS cho phép thao tác này. Hàm trả một `boolean` cho biết có bật được hay không, vì vậy mã thư viện nên kiểm tra kết quả thay vì bỏ qua.

~~~java
if (!member.trySetAccessible()) {
    throw new IllegalStateException("Cannot enable reflective access");
}
~~~

Đoạn trên là **mã minh họa**, với `member` là `AccessibleObject` hợp lệ. Trường hợp trong bài sẽ thành công vì caller và target ở cùng module; trong thiết kế tổng quát cần xử lý cả trường hợp từ chối, đặc biệt khi thay đổi kiến trúc module hoặc caller.

### `setAccessible(true)`

Cũng yêu cầu bỏ qua kiểm tra truy cập Java, nhưng khi yêu cầu không được phép, `setAccessible(true)` có thể ném `java.lang.reflect.InaccessibleObjectException`. `trySetAccessible()` thường thuận tiện hơn nếu bạn muốn kiểm tra khả năng truy cập mà không xử lý ngoại lệ cho trường hợp JPMS từ chối. `setAccessible(false)` đưa trạng thái cờ về mặc định.

**Lưu ý:** bật flag trên **đối tượng `Field`/`Method`/`Constructor` cụ thể**; nó không đổi modifier trong khai báo `private`, không chuyển class thành `public`, không sửa `module-info.java` và không làm mọi đối tượng Reflection khác tự động được mở quyền.

## 6. Điều gì được phép và điều gì vẫn bị giới hạn?

| Tình huống | Cùng module thì sao? | Giải thích |
| --- | --- | --- |
| `public` class và `public` member ở hai package khác nhau | Có thể truy cập bình thường theo luật Java | `exports` không bắt buộc giữa các package **nội bộ module** |
| `private` field/method/constructor khai báo ở lớp khác | Không có quyền trực tiếp chỉ vì cùng module | Có thể tìm qua `getDeclared...` và thử bật quyền Reflection |
| Package-private class ở package khác | Mã Java bên ngoài package không thể trực tiếp gọi bằng tên lớp theo cách thông thường | Reflection có thể tìm bằng tên ở runtime và mở quyền sâu khi thỏa *same module* |
| `protected` member ở package khác | Vẫn áp dụng quy tắc `protected` của Java | Cùng module không thay thế yêu cầu kế thừa/cách dùng receiver |
| `final` field | Có thể được cấp quyền đọc sâu; sửa giá trị có các hạn chế riêng | Đặc biệt các field `static final`, field `final` của record và hidden class không thể ghi chỉ nhờ `setAccessible(true)` |
| Thành viên `static` | Tra cứu/bật quyền vẫn theo các quy tắc trên | Các thao tác kiểm tra/gọi với receiver `null` khi API yêu cầu |
| Một utility thực hiện Reflection từ module khác | Phải xét **module của utility thực sự gọi** | Việc request khởi phát từ module đích không đủ để tạo quyền same-module cho utility |

Đối với `final`, đừng coi việc `trySetAccessible()` thành công là bảo đảm `Field#set` sẽ ghi được. Tài liệu Java phân biệt quyền **đọc** với khả năng **ghi** vào field final không thể sửa; ngoài ra thay đổi field final bằng Reflection có thể vi phạm giả định tối ưu hóa và tính bất biến của đối tượng.

### Package-private class ở package khác cùng module

Giả sử có `lesson.domain.Internal` là một **top-level class package-private**. Mã trong `lesson.app` không thể `import lesson.domain.Internal;` rồi dùng trực tiếp kiểu đó. Tuy nhiên một công cụ Reflection chạy trong cùng module có thể tìm class bằng tên runtime phù hợp, lấy `Class<?>`, đọc metadata, rồi xét quyền truy cập phù hợp. Không nên coi việc Reflection cấp quyền là lý do để bỏ thiết kế API rõ ràng khi chỉ cần dữ liệu `public`.

## 7. Chú ý tới module của nơi gọi API, không chỉ luồng nghiệp vụ

Xét một ứng dụng trong module `business.app`:

~~~text
business.app
  ├── business.Secret
  └── business.Main
reflection.helper
  └── helper.Accessor
~~~

Nếu `business.Main` trực tiếp gọi `field.trySetAccessible()` cho field của `business.Secret`, điều kiện module có thể là *same module*. Nhưng nếu `Main` giao đối tượng `Field` cho `helper.Accessor` rồi **chính `Accessor`** gọi `trySetAccessible()`, caller lúc đó thuộc `reflection.helper`. Việc cấp phép bị xét lại theo module của caller ở thời điểm gọi; nếu package đích không mở phù hợp, yêu cầu deep reflection có thể không được chấp thuận.

Ví dụ kiến trúc trên chỉ minh họa sự khác biệt, không phải chương trình chạy độc lập. Khi dùng thư viện serialization, dependency injection, mapper hoặc test framework, cần xác định **lớp trong module nào thực hiện lời gọi Reflection**. Đây là lý do code hoạt động khi viết trực tiếp trong module ứng dụng nhưng có thể thất bại khi được chuyển sang helper library ở module khác.

## 8. Những lỗi thường gặp

1. **Đồng nhất "cùng module" với "cùng package".** JPMS không thay đổi phạm vi package-private và các quy tắc `protected`. Hai package nội bộ là hai package khác nhau.
2. **Cho rằng `getDeclaredField()` trả về `Field` tức là đã được đọc.** Lookup thành công chỉ xác nhận tồn tại metadata; phải xét `canAccess` hoặc bật quyền hợp lệ trước thao tác `get`/`set`.
3. **Cho rằng `getDeclaredMethod()` tự tìm method kế thừa.** API "declared" tìm thành viên do chính lớp khai báo; nếu cần method `public` được kế thừa, cân nhắc `getMethod()`. Điều này độc lập với JPMS.
4. **Thêm `exports` hoặc `opens` chỉ vì có hai package trong cùng module.** Trong cùng module, quyền internal source access và nhánh same-module của Reflection đã có quy tắc riêng.
5. **So sánh `Module#getName()` thay cho đối tượng `Module`.** Với unnamed module, `getName()` có thể là `null` cho nhiều module khác nhau. Hãy dùng `==` nếu mục tiêu là xác minh chính xác same module.
6. **Không kiểm tra giá trị của `trySetAccessible()`.** Hàm trả `boolean`, còn việc đổi module, đổi vị trí helper hoặc dùng module khác có thể khiến yêu cầu không còn đủ điều kiện.
7. **Dùng sai receiver của `canAccess`.** Constructor và static member yêu cầu `null`; instance member yêu cầu đối tượng instance đúng loại.
8. **Cho rằng được bật access là có thể sửa `static final`.** Reflection không biến mọi field bất biến thành field có thể ghi; hạn chế non-modifiable final vẫn tồn tại.
9. **Dựa vào `--add-opens` để chạy ví dụ same-module.** Ví dụ trong bài không cần tham số đó; nếu phải mở package, cần xem lại module chứa caller thực sự và ranh giới ứng dụng.

## 9. Tự kiểm tra

**Câu 1.** Trong named module `demo.same`, `lesson.app.Main` có được gọi `public static Vault.create()` từ `lesson.domain.Vault` khi `module-info.java` không có `exports lesson.domain;`?

**Trả lời:** Có, nếu `Vault` và method là `public` và cả hai package cùng module. `exports` liên quan chủ yếu đến truy cập từ module khác.

**Câu 2.** Nếu `token` là `private`, vì sao `getDeclaredField("token")` tìm được mà `field.canAccess(vault)` ban đầu trả `false`?

**Trả lời:** Lookup trả metadata cả của private member khai báo trực tiếp; còn `canAccess` xét quyền sử dụng theo quy tắc Java và trạng thái accessibility hiện tại. `Main` là lớp khác, không có quyền private thông thường của `Vault`.

**Câu 3.** Khi `Main` và `Vault` cùng module, `trySetAccessible()` trên private field có thể trả gì?

**Trả lời:** Trong điều kiện bình thường của ví dụ, trả `true` do nhánh cấp phép same-module. Sau đó có thể đọc bằng `Field#get`; không suy ra rằng mọi phép ghi vào final field cũng hợp lệ.

**Câu 4.** Nếu helper ở module khác thực hiện `trySetAccessible()` thì vẫn là "same-module" vì `Main` gọi helper không?

**Trả lời:** Không. Điều kiện xét lớp **thực hiện lời gọi** cùng module với declaring class. Phải đánh giá quyền của helper ở module khác theo quy tắc JPMS tương ứng.

**Câu 5.** Có thể kiểm tra chính xác hai lớp cùng module bằng cách nào?

**Trả lời:** `First.class.getModule() == Second.class.getModule()`. Đừng chỉ đối chiếu tên module, nhất là với unnamed module và nhiều class loader.

**Ghi nhớ:** *cùng module* mở ra khả năng Reflection bỏ qua kiểm tra truy cập Java vào các thành viên của module ấy, nhưng **không làm mất quy tắc `private`/`protected`/package-private của Java source**. Luồng đúng là xác minh module của caller, tìm thành viên theo tên/chữ ký, kiểm tra trạng thái truy cập, bật quyền khi thật sự cần và được phép, rồi mới đọc/gọi/khởi tạo.
