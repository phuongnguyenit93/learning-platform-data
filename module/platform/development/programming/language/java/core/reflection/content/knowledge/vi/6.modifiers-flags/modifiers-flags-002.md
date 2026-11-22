# public, protected, private và package-private trong Java Reflection

## 1. Mục tiêu và bối cảnh

Khi dùng Java Reflection để khám phá một lớp ở thời điểm chạy, hai câu hỏi cần tách bạch:

1. **Thành viên được khai báo với mức truy cập nào?** Đọc cờ của lớp, phương thức, trường hoặc constructor qua `getModifiers()` và `java.lang.reflect.Modifier`.
2. **Mã hiện tại có thể sử dụng thành viên đó không?** Quy tắc truy cập của Java vẫn được kiểm tra khi gọi phương thức, đọc/ghi trường hoặc tạo đối tượng qua reflection. Việc tìm thấy một thành viên không tự động cấp quyền sử dụng nó.

Ví dụ, `getDeclaredMethod("secretCode")` có thể tìm một phương thức `private`; lời gọi `Method.invoke(...)` từ một lớp bên ngoài vẫn có thể ném `IllegalAccessException`.

Bài này tập trung vào **bốn mức truy cập**, cách đọc chúng qua reflection, khác biệt giữa API lấy thành viên `get...` và `getDeclared...`, cùng giới hạn của việc vượt kiểm tra truy cập. Các cờ khác như `static`, `final`, `abstract` chỉ được nhắc khi cần phân biệt với access modifier.

## 2. Quy tắc truy cập của ngôn ngữ Java

| Mức truy cập | Khai báo | Ai có thể truy cập theo quy tắc ngôn ngữ? |
| --- | --- | --- |
| `public` | Có từ khóa `public` | Mã ở mọi package, miễn chính kiểu khai báo cũng có thể truy cập; module có thể bổ sung ranh giới `exports`. |
| `protected` | Có từ khóa `protected` | Mã trong cùng package; ngoài package, mã của lớp con được phép trong những điều kiện của quy tắc `protected`, bao gồm giới hạn về đối tượng nhận đối với thành viên instance. |
| package-private | **Không** viết từ khóa truy cập | Mã trong cùng package. “Default access” đôi khi được dùng để gọi mức này nhưng không tồn tại từ khóa `package-private` trong Java. |
| `private` | Có từ khóa `private` | Chỉ trong phạm vi kiểu khai báo và các kiểu lồng nhau có quyền truy cập tương ứng theo quy tắc Java. |

Các điểm dễ nhầm:

- **Cùng package không có nghĩa là cùng thư mục bất kỳ:** package xác định bởi khai báo `package`; `com.example` và `com.example.internal` là hai package khác nhau.
- **`protected` không có nghĩa là mọi mã ngoài package đều dùng được:** quan hệ kế thừa và kiểu của biểu thức tham chiếu đến đối tượng đều có thể ảnh hưởng tới quyền truy cập.
- **`private` không có nghĩa reflection không nhìn thấy:** Reflection có thể đọc thông tin khai báo; thao tác sử dụng lại là bước riêng.
- **Mức truy cập của lớp và của thành viên cùng có tác dụng:** một phương thức `public` nằm trong kiểu top-level package-private không tự biến kiểu đó thành công khai đối với mã ở package khác.
- Kiểu top-level chỉ có thể khai báo `public` hoặc package-private. Các kiểu thành viên lồng trong kiểu khác có thể khai báo `protected` hoặc `private`; lớp cục bộ và lớp vô danh có quy tắc riêng.

## 3. Đọc mức truy cập bằng Modifier

Các đối tượng `Class<?>`, `Method`, `Field` và `Constructor<?>` đều cung cấp `getModifiers()`, trả về một **bit mask `int`**. Dùng phương thức kiểm tra bit thay vì so sánh số cờ với một hằng duy nhất:

~~~java
int flags = method.getModifiers();

if (Modifier.isPublic(flags)) {
    // public
} else if (Modifier.isProtected(flags)) {
    // protected
} else if (Modifier.isPrivate(flags)) {
    // private
} else {
    // package-private đối với access modifier của method
}
~~~

Đoạn trên là mã minh họa trong một ngữ cảnh đã có biến `method` và import `java.lang.reflect.Modifier`; chương trình hoàn chỉnh nằm ở phần 5.

- `Modifier.isPublic(flags)`, `isProtected(flags)`, `isPrivate(flags)` kiểm tra đúng từng bit truy cập.
- **Không có `Modifier.isPackagePrivate(...)`.** Với một phương thức/trường/constructor/lớp mà mức truy cập được xét, package-private nghĩa là *không có cả ba bit* `public`, `protected`, `private`.
- `Modifier.toString(flags)` biểu diễn chuỗi từ khóa mà mask mang theo. Nếu chỉ có quyền package-private và không có cờ khác, chuỗi có thể rỗng (`""`). Nếu có cờ `static` hoặc `final`, chuỗi có thể chứa các từ đó; do vậy không kết luận rằng `toString(flags)` rỗng mới là package-private.
- `flags == Modifier.PUBLIC` dễ sai: một phương thức `public static` có cả bit `PUBLIC` và `STATIC`; hãy dùng `Modifier.isPublic(flags)`.

Ví dụ:

~~~java
Method method = SomeClass.class.getDeclaredMethod("run");
System.out.println(Modifier.toString(method.getModifiers()));
~~~

Đây cũng là mã minh họa, giả sử `SomeClass` khai báo `run()` không tham số. Nếu phương thức có khai báo `public static void run()`, chuỗi in ra là `public static`. Không dựa vào thứ tự của các phần tử `getDeclaredMethods()` khi sinh báo cáo; API không cam kết thứ tự.

## 4. Tìm thành viên khác với được quyền truy cập

| API của `Class` | Thành viên có thể tìm thấy | Phạm vi kế thừa |
| --- | --- | --- |
| `getMethod(name, parameterTypes...)` / `getMethods()` | Phương thức `public` | Bao gồm các phương thức public được kế thừa theo quy tắc của API |
| `getDeclaredMethod(name, parameterTypes...)` / `getDeclaredMethods()` | Mọi mức truy cập, miễn khai báo trong chính lớp/interface đó | Không tự tìm trong lớp cha |
| `getField(name)` / `getFields()` | Trường `public` | Có tính đến các trường public được kế thừa |
| `getDeclaredField(name)` / `getDeclaredFields()` | Mọi mức truy cập của trường khai báo trực tiếp | Không tìm trong lớp cha |
| `getConstructor(parameterTypes...)` / `getConstructors()` | Constructor `public` | Constructor không được kế thừa |
| `getDeclaredConstructor(parameterTypes...)` / `getDeclaredConstructors()` | Constructor khai báo trực tiếp, mọi mức truy cập | Constructor không được kế thừa |

Ví dụ: với một phương thức `private void check()`, `getDeclaredMethod("check")` có thể trả về `Method`, trong khi `getMethod("check")` ném `NoSuchMethodException`. Ngoại lệ *không tìm thấy* (`NoSuchMethodException`) khác với ngoại lệ *không có quyền gọi* (`IllegalAccessException`).

Chữ ký phương thức còn chứa danh sách kiểu tham số: nếu có `void check(String value)`, cần gọi `getDeclaredMethod("check", String.class)`; chỉ truyền `"check"` sẽ không tìm thấy phương thức một tham số. Với phương thức overload, luôn truyền đúng kiểu tham số.

Sau khi đã tìm được `Method`, `Field` hoặc `Constructor`, Java vẫn kiểm tra tính hợp lệ khi `invoke(...)`, `get(...)`, `set(...)` hoặc `newInstance(...)`. Đọc metadata không đồng nghĩa với quyền gọi/đọc/ghi.

## 5. Chương trình Java 17 chạy được: đọc và thử truy cập cả bốn mức

Ta đặt lớp chứa thành viên trong package `lesson.api`, còn mã reflection trong package `lesson.client` để thấy rõ việc vượt ranh giới package.

**Tệp 1 — `src/lesson/api/MemberBox.java`:**

~~~java
package lesson.api;

public class MemberBox {
    public String publicCode() { return "public value"; }
    protected String protectedCode() { return "protected value"; }
    String packageCode() { return "package value"; }
    private String secretCode() { return "private value"; }
}
~~~

**Tệp 2 — `src/lesson/client/ReflectAccess.java`:**

~~~java
package lesson.client;

import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import lesson.api.MemberBox;

public class ReflectAccess {
    public static void main(String[] args) throws Exception {
        Class<MemberBox> type = MemberBox.class;
        for (String name : new String[] {
                "publicCode", "protectedCode", "packageCode", "secretCode" }) {
            Method method = type.getDeclaredMethod(name);
            System.out.println(name + ": " + visibility(method.getModifiers()));
        }

        System.out.println("getMethod(publicCode): "
                + type.getMethod("publicCode").getName());
        try {
            type.getMethod("secretCode");
        } catch (NoSuchMethodException ex) {
            System.out.println("getMethod(secretCode): not found");
        }

        MemberBox box = new MemberBox();
        Method secret = type.getDeclaredMethod("secretCode");
        try {
            secret.invoke(box);
        } catch (IllegalAccessException ex) {
            System.out.println("invoke before override: IllegalAccessException");
        }
        boolean opened = secret.trySetAccessible();
        System.out.println("trySetAccessible(secretCode): " + opened);
        if (opened) {
            System.out.println("invoke after override: " + secret.invoke(box));
        }
    }

    private static String visibility(int flags) {
        if (Modifier.isPublic(flags)) return "public";
        if (Modifier.isProtected(flags)) return "protected";
        if (Modifier.isPrivate(flags)) return "private";
        return "package-private";
    }
}
~~~

**Biên dịch và chạy từ thư mục chứa `src/` (Java 17 trở lên, dùng classpath):**

~~~bash
mkdir -p out
javac --release 17 -d out src/lesson/api/MemberBox.java src/lesson/client/ReflectAccess.java
java -cp out lesson.client.ReflectAccess
~~~

Trên PowerShell, có thể thay `mkdir -p out` bằng `New-Item -ItemType Directory -Force out`. Thư mục `out` chứa các file `.class` đúng cấu trúc package.

**Stdout chính xác trong ví dụ classpath trên:**

~~~text
publicCode: public
protectedCode: protected
packageCode: package-private
secretCode: private
getMethod(publicCode): publicCode
getMethod(secretCode): not found
invoke before override: IllegalAccessException
trySetAccessible(secretCode): true
invoke after override: private value
~~~

**Giải thích kết quả:**

1. `getDeclaredMethod` truy xuất được cả bốn khai báo, nên ta đọc được bốn mức bằng `getModifiers()`.
2. `getMethod("publicCode")` tìm thành viên công khai; `getMethod("secretCode")` không tìm thành viên private và ném `NoSuchMethodException`.
3. `ReflectAccess` ở package khác và không thuộc phạm vi được phép truy cập `private secretCode()`; lời gọi `invoke` ban đầu ném `IllegalAccessException`.
4. `trySetAccessible()` trả về `true` ở đây vì cả hai lớp là mã trên classpath, thuộc unnamed module, và không có rào cản module ngăn truy cập sâu. Khi thành công, cùng đối tượng `Method` có thể được gọi bằng `invoke`. Điều này **không bảo đảm** sẽ thành công với mọi lớp trong named module hoặc thư viện khác.

Nếu muốn thử phương thức `protectedCode` hoặc `packageCode`, đổi tên khi lấy `getDeclaredMethod`. Từ `lesson.client.ReflectAccess`, thao tác `invoke` thông thường cũng bị kiểm tra truy cập; có metadata không làm mã trở thành lớp con hay cùng package.

## 6. `canAccess`, `trySetAccessible` và hệ thống module

Java cung cấp ba thao tác thường gặp trên đối tượng reflective:

- `method.canAccess(receiver)`: hỏi tại thời điểm đó caller hiện tại có thể truy cập bằng đối tượng `Method` này không; dùng `receiver` là instance đúng loại cho phương thức instance, hoặc `null` cho phương thức static. Đối với trường hoặc constructor, tham số nhận cũng phải đúng theo hợp đồng API tương ứng.
- `method.trySetAccessible()`: **thử** tắt việc kiểm tra quyền truy cập của ngôn ngữ Java đối với đối tượng reflection; trả về `true` nếu thành công và `false` khi không thể bật quyền này vì giới hạn truy cập. Trong một số tình huống có thể xuất hiện ngoại lệ bảo mật.
- `method.setAccessible(true)`: yêu cầu tắt kiểm tra truy cập; nếu rào cản module không cho phép, có thể ném `java.lang.reflect.InaccessibleObjectException`.

Từ Java 9, JPMS (Java Platform Module System) phân biệt:

| Khai báo module | Ý nghĩa thực tế |
| --- | --- |
| `exports p;` | Cho phép module khác sử dụng các kiểu `public` và thành viên `public` có thể truy cập của package `p` qua API thông thường; không mặc nhiên cho phép reflection mở thành viên private. |
| `opens p;` | Cho phép truy cập sâu bằng reflection vào package `p` theo cơ chế mở package, bao gồm thành viên không public khi thao tác hợp lệ. |
| Không `exports` hay `opens` | Mã ở module khác thường bị hạn chế hơn, kể cả khi reflection thấy tên thành viên. |

Có thể mở có mục tiêu một package khi chạy để chẩn đoán, ví dụ tùy cấu hình: `--add-opens java.base/java.lang=ALL-UNNAMED`. Đây là một cơ chế cấp phép mạnh; không nên thêm rộng khắp hoặc dựa vào nó như thiết kế API bình thường. Với mã ở các named module khác nhau, kết quả `trySetAccessible()` phụ thuộc quan hệ module, package và quyền mở thực tế.

**Không nhầm `AccessibleObject` với thay đổi khai báo:** gọi `trySetAccessible` không biến phương thức private thành public trong class file. `method.getModifiers()` vẫn báo `private`. Nó chỉ ảnh hưởng việc kiểm tra quyền trên đối tượng reflection được điều chỉnh trong phạm vi được phép. Các giới hạn khác như tính bất biến của một số trường `final` vẫn tồn tại.

## 7. Sai lầm thường gặp và cách xử lý

| Hiểu nhầm / lỗi | Vì sao sai | Cách làm |
| --- | --- | --- |
| `getMethods()` trả về mọi phương thức | Nó chỉ chọn phương thức public theo quy tắc API | Dùng `getDeclaredMethods()` khi cần xem các khai báo không public, và duyệt lớp cha riêng nếu cần |
| `getDeclaredMethods()` chứa cả khai báo lớp cha | Nó chỉ trả về phương thức khai báo trong chính lớp/interface đang hỏi | Duyệt `getSuperclass()` và `getDeclaredMethods()` từng cấp nếu đó là mục tiêu |
| Tìm được `Method` tức là gọi được | Khám phá metadata và quyền thực thi là hai bước khác nhau | Phân biệt `NoSuchMethodException`, `IllegalAccessException`, `InvocationTargetException` |
| `Modifier.toString(flags).isEmpty()` là cách duy nhất nhận package-private | Một khai báo package-private vẫn có thể mang cờ như `static` hoặc `final` | Kiểm tra cả ba bit `public/protected/private` đều không có |
| `flags == Modifier.PUBLIC` nhận diện mọi public method | Một method có thể đồng thời là `public static` hoặc `public final` | Dùng `Modifier.isPublic(flags)` |
| `protected` luôn truy cập được từ package khác nếu có subclass ở đâu đó | Quy tắc kiểm tra dựa trên vị trí mã truy cập và đối tượng nhận, không chỉ sự tồn tại của subclass | Kiểm tra ngữ cảnh package/kế thừa của chính caller |
| `setAccessible(true)` luôn thành công | Module có thể không mở package cho caller | Ưu tiên API public; nếu cần, thiết kế `opens` có chủ đích và xử lý thất bại |
| `private` là “bảo mật dữ liệu tuyệt đối” | Modifier chủ yếu là ranh giới đóng gói API ở cấp ngôn ngữ, không phải cơ chế bảo mật mọi môi trường chạy | Dùng các cơ chế bảo mật phù hợp cho dữ liệu nhạy cảm, đồng thời giữ đóng gói tốt |

Khi tìm phương thức trên lớp kế thừa, hãy phân biệt `getMethod` có thể tìm public method kế thừa với `getDeclaredMethod` chỉ tìm khai báo trực tiếp. Khi in danh sách `getDeclaredMethods()`, sắp xếp theo tên/chữ ký nếu cần đầu ra ổn định vì thứ tự mảng reflection không được bảo đảm.

## 8. Bài tập tự kiểm tra

1. Thêm `public static String sharedCode()` vào `MemberBox`. Dự đoán kết quả `Modifier.isPublic(method.getModifiers())` và `Modifier.toString(method.getModifiers())`. **Đáp án:** `true`; chuỗi chứa `public static`.
2. Thêm `private MemberBox(int seed)` bên cạnh constructor không tham số được khai báo tường minh là public. Hỏi `getConstructor(int.class)` và `getDeclaredConstructor(int.class)` khác nhau ra sao? **Đáp án:** API thứ nhất ném `NoSuchMethodException`, API thứ hai tìm được constructor private nhưng việc gọi còn phải kiểm tra quyền truy cập.
3. Chuyển `ReflectAccess` vào package `lesson.api`. Với `packageCode()`, thao tác `invoke` có được phép không? **Đáp án:** được phép nếu lớp gọi đúng cùng package và nhận đúng đối tượng; với `private`, ranh giới private vẫn còn.
4. Chuyển `MemberBox` sang named module có package không mở. Có thể kết luận `trySetAccessible()` chắc chắn trả về `true` như ví dụ classpath không? **Đáp án:** không; cần xét package được mở cho module của caller hay chưa.

**Ghi nhớ:** Reflection có thể *quan sát* các mức truy cập qua `getModifiers()`, nhưng thao tác thực tế vẫn phải vượt qua phép kiểm tra quyền của Java và ranh giới module. Hãy chọn `getDeclared...` để khám phá khai báo nội bộ, `get...` để tìm thành viên public phù hợp, và chỉ yêu cầu truy cập sâu khi thực sự cần thiết.
