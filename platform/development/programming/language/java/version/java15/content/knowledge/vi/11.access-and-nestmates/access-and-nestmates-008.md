# Kiểm thử truy cập hợp lệ, sai package và thiếu quyền khi định nghĩa hidden class (Java 15+)

## 1. Mục tiêu bài học

Từ Java 15, **hidden class (lớp ẩn)** là tính năng chính thức của JVM. Một trường hợp sử dụng thường gặp là framework tạo lớp triển khai tại thời điểm chạy mà không muốn lớp ấy có tên nhị phân để tìm lại bằng cơ chế nạp lớp thông thường. API trọng tâm là:

~~~java
MethodHandles.Lookup.defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
~~~

Phương thức trả về một **`MethodHandles.Lookup` mới** có `lookupClass()` chính là hidden class vừa được tạo. Nó **không** tùy tiện nhận một class file rồi định nghĩa ở bất kỳ package nào: Java kiểm tra **quyền của `Lookup`**, **package của tên lớp trong class file**, và các điều kiện xác minh/liên kết bytecode.

Đề bài này tập trung vào **ba nhánh kiểm thử riêng biệt**:

1. **Truy cập hợp lệ:** `Lookup` có *full privilege* và bytes thuộc **cùng package** với `lookupClass()`. Kết quả: tạo hidden class thành công, có thể tạo `MethodHandle` cho phương thức thích hợp.
2. **Sai package:** `Lookup` đủ quyền nhưng class file chứa tên lớp thuộc package khác. Kết quả mong đợi: `IllegalArgumentException`.
3. **Thiếu quyền:** bytes hợp lệ, đúng package, nhưng `Lookup` không có đủ đặc quyền. Kết quả mong đợi: `IllegalAccessException`.

Vì nhóm cha là **Truy cập và nest**, bài còn kiểm thử một điều kiện khác rất dễ nhầm: **cùng package không có nghĩa cùng nest**. Muốn hidden class truy cập thành viên `private` của lớp chủ qua quyền nestmate, phải thiết lập `ClassOption.NESTMATE` khi phù hợp.

Mã thực hành dùng các API **còn được hỗ trợ trên Java hiện đại**, chạy với **JDK 17 trở lên**, không cần chế độ preview hoặc các API nội bộ.

## 2. Các khái niệm cần hiểu trước khi kiểm thử

### Lookup là ngữ cảnh kiểm tra truy cập

`MethodHandles.lookup()` trả về `Lookup` dựa trên **lớp thực sự gọi phương thức** (*caller-sensitive*). Đối tượng `Lookup` mang theo ngữ cảnh lớp, module và các **lookup mode** để kiểm tra quyền khi yêu cầu tạo `MethodHandle` hoặc định nghĩa lớp.

~~~java
MethodHandles.Lookup owner = MethodHandles.lookup();

Class<?> context = owner.lookupClass();
boolean hasAllRights = owner.hasFullPrivilegeAccess();
~~~

Trong thuật ngữ API hiện hành, **full privilege access** yêu cầu có cả mode **`PRIVATE` và `MODULE`**. Đó là điều kiện thiết yếu của `defineHiddenClass(...)`. Ngược lại, `publicLookup()` cố ý có năng lực hạn chế, và `dropLookupMode(...)` chỉ **giảm**, không phục hồi quyền.

Một `Lookup` không phải “mật khẩu” dưới dạng chuỗi. Nó là **capability object**: trao cho code khác một `Lookup` hoặc `MethodHandle` có đặc quyền có thể mở ra các thao tác mà bên nhận không tự tạo được.

### Package, runtime package, module và nest khác nhau

| Khái niệm | Ý nghĩa khi kiểm tra hidden class |
| --- | --- |
| **Package ghi trong class file** | Tên nội bộ của class phải thuộc package trùng với `lookupClass()` của `Lookup` dùng để định nghĩa. Đây là điều kiện về class bytes, không phải chỉ về vị trí file trên đĩa. |
| **Runtime package** | JVM xem package trong quan hệ với defining class loader; package có thể chi phối quyền `package-private`. |
| **Module** | Hidden class được định nghĩa trong module của lookup class. Quyền truy cập giữa named modules còn chịu quy tắc `reads`, `exports` và `opens` của JPMS. |
| **Nest** | Tập hợp các lớp được phép truy cập `private` của nhau theo cơ chế nestmate. **Cùng package/module không tự tạo quan hệ nest**. |

Theo Java Language Specification/JVM, một thành viên `private` thường chỉ khả dụng cho chính lớp và các nestmate hợp lệ. Vì vậy **định nghĩa hidden class thành công** và **truy cập private của lớp chủ thành công** là **hai phép thử khác nhau**.

## 3. Kết quả lỗi cần dự đoán trước

| Tình huống độc lập | Dữ liệu bytes | `Lookup` | Kết quả mong đợi |
| --- | --- | --- | --- |
| Thành công | Class file `demo.access.HiddenAccessChecks$Template` | `MethodHandles.lookup()` gọi từ `demo.access.HiddenAccessChecks` | `defineHiddenClass` thành công, `isHidden()==true`. |
| Sai package | Class file `demo.foreign.ForeignTemplate` | Cùng `owner` **có full privilege** | `IllegalArgumentException`. |
| Thiếu quyền public-only | Bytes local **đúng package** | `MethodHandles.publicLookup()` | `IllegalAccessException`. |
| Thiếu quyền sau khi drop mode | Bytes local **đúng package** | `owner.dropLookupMode(PRIVATE)` | `IllegalAccessException`. |
| Không phải nestmate | Hidden class tạo thành công, **không** chỉ định `NESTMATE` | `Lookup` của hidden class | Tra cứu `private` của lớp chủ bị `IllegalAccessException`. |
| Có nestmate | Hidden class tạo với `ClassOption.NESTMATE` | `Lookup` của hidden class vừa tạo | Có thể tạo handle cho `private` của lớp chủ khi các điều kiện truy cập khác thỏa mãn. |

**Quan trọng khi thiết kế test:** nên giữ **chỉ một điều kiện sai** trong mỗi ca âm tính. Nếu một thao tác vừa dùng bytes sai package vừa dùng `Lookup` thiếu quyền, không nên khẳng định Java bắt buộc báo ngoại lệ “sai package” trước: các bước kiểm tra có thứ tự, và một lỗi khác có thể che lỗi mà bạn đang định đo.

Đừng suy đoán rằng chỉ cần khai báo source file ở thư mục bất kỳ sẽ tạo sai package. Package của class file được xác định từ khai báo `package ...;` trong mã và tên lớp ở class file. Trong bài thực hành, hai file có **hai package khác nhau thật sự**.

## 4. Vì sao lỗi sai package là IllegalArgumentException?

Giả sử lớp chủ khai báo:

~~~java
package demo.access;
~~~

và nó gọi `MethodHandles.lookup()`. Bytecode của hidden class được đưa cho `owner.defineHiddenClass(...)` phải mô tả một class ở **`demo.access`**. Nếu bytes thực sự là của:

~~~java
package demo.foreign;
public class ForeignTemplate { }
~~~

thì điều kiện package không được đáp ứng. Dù `owner.hasFullPrivilegeAccess()` là `true`, cách định nghĩa đó vẫn bị từ chối bằng `IllegalArgumentException`.

Đây là **ràng buộc đầu vào của API**, không phải một tình huống có thể khắc phục bằng cách đổi tên mảng bytes hoặc chuyển file `.class` sang thư mục khác. Java đọc **tên class trong class file**, không lấy package từ tên biến hoặc chuỗi resource path.

Muốn tạo lớp ẩn thuộc `demo.foreign` một cách hợp lệ, phía gọi phải có **`Lookup` được cấp phép thật sự trong ngữ cảnh phù hợp của package đó**, cùng các điều kiện khác của API. Không thể lấy một `publicLookup()` rồi tự chọn target package để vượt kiểm tra.

## 5. Vì sao thiếu quyền là IllegalAccessException?

### 5.1. publicLookup không đủ để định nghĩa hidden class

`MethodHandles.publicLookup()` dành cho khả năng tra cứu công khai có giới hạn. Nó **không** có full privilege và không có quyền tự định nghĩa hidden class bằng `defineHiddenClass`.

~~~java
MethodHandles.publicLookup().defineHiddenClass(localBytes, false);
// IllegalAccessException, kể cả khi localBytes hợp lệ và đúng package.
~~~

Đây chỉ là một **đoạn minh họa**, giả sử `localBytes` đã được nạp như trong chương trình đầy đủ ở mục 8.

### 5.2. Giảm quyền của một Lookup hợp lệ

~~~java
MethodHandles.Lookup owner = MethodHandles.lookup();
MethodHandles.Lookup reduced =
        owner.dropLookupMode(MethodHandles.Lookup.PRIVATE);

boolean full = reduced.hasFullPrivilegeAccess(); // false
reduced.defineHiddenClass(localBytes, false);   // IllegalAccessException
~~~

Việc xóa mode `PRIVATE` khiến lookup không còn **full privilege**. Dù bytes vẫn thuộc đúng package, `defineHiddenClass` bị từ chối. `dropLookupMode` có thể ảnh hưởng đến các mode còn lại theo quy tắc API; **không nên chỉ dựa vào số bit tự suy đoán**, hãy kiểm tra `lookupModes()`/`hasFullPrivilegeAccess()` và nguyên tắc của Javadoc.

Không có lời gọi `in(Target.class)` hoặc `dropLookupMode(...)` nào có thể biến một lookup bị hạn chế thành lookup toàn quyền. `MethodHandles.privateLookupIn(...)` cũng có kiểm tra quyền/module riêng, **không phải cơ chế nâng quyền tùy ý**.

## 6. Cùng package không tự động có quyền private: kiểm thử nest

Sau khi định nghĩa:

~~~java
MethodHandles.Lookup hidden = owner.defineHiddenClass(localBytes, true);
~~~

ta nhận được `Lookup` có quyền đầy đủ **đối với hidden class mới**. Tuy nhiên, nếu không chọn `NESTMATE`, hidden class mặc định ở một nest của riêng nó. Ví dụ, tra cứu phương thức private `HiddenAccessChecks.secret()` thông qua `hidden.findStatic(...)` vẫn bị `IllegalAccessException`.

~~~java
hidden.findStatic(
        HiddenAccessChecks.class,
        "secret",
        MethodType.methodType(String.class));
// Không cùng nest: IllegalAccessException.
~~~

Nếu có nhu cầu hợp lệ để hidden class làm **nestmate** của lớp chủ:

~~~java
MethodHandles.Lookup nestmate = owner.defineHiddenClass(
        localBytes,
        true,
        MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

thì hidden class gia nhập nest chứa lookup class, và có thể tạo handle để truy cập `private` của các thành viên nest trong điều kiện thích hợp. Điều đó **không** cho phép truy cập `private` của mọi lớp trong module.

**Phân biệt hai option:**

- `NESTMATE`: điều khiển quan hệ nest và quyền truy cập private theo nestmate.
- `STRONG`: ảnh hưởng quan hệ sống còn giữa hidden class và defining class loader. Nó **không tự cấp quyền private** và không thay thế `NESTMATE`.

Đây là lý do bộ kiểm thử cần có **hai tình huống**: hidden class không có `NESTMATE` phải bị từ chối khi truy cập private của lớp chủ; hidden class tạo có `NESTMATE` thì phép truy cập tương ứng thành công.

## 7. Thiết kế kiểm thử có thể thất bại đúng nghĩa

Một phép thử âm tính tốt không chỉ in “UNEXPECTED” rồi tiếp tục. Nó cần **thất bại ngay** nếu:

- Không có ngoại lệ nào xảy ra ở ca dự kiến phải ném ngoại lệ.
- Ngoại lệ xảy ra **khác loại** được mong đợi (ví dụ một lỗi nạp resource hoặc lỗi class file bị nhầm thành lỗi quyền).
- Một ca tích cực tạo lớp thành công nhưng không đáp ứng bất biến như `isHidden()` hoặc không gọi được phương thức.

Ví dụ sử dụng helper:

~~~java
@FunctionalInterface
interface CheckedAction {
    void run() throws Throwable;
}
~~~

và `expect(label, expected, action)` để kiểm tra **đúng loại ngoại lệ**. Helper sẽ ném `AssertionError` nếu không nhận được ngoại lệ hoặc nhận sai loại. Các ca tích cực dùng `verify(label, condition)` để ném `AssertionError` khi bất biến sai. Bởi vậy bộ kiểm thử **không phụ thuộc JVM flag `-ea`**, vốn chỉ áp dụng cho từ khóa Java `assert`.

Mỗi ca ghi nhận một lần thành công và dòng cuối sẽ in tổng số ca đã vượt qua. Trong chương trình đầy đủ bên dưới có **13 kiểm tra**.

## 8. Ví dụ đầy đủ: hai package, biên dịch và kiểm thử Java 17+

Tạo đúng cấu trúc thư mục sau:

~~~text
project/
  src/
    demo/
      access/
        HiddenAccessChecks.java
      foreign/
        ForeignTemplate.java
~~~

### Tệp 1 — src/demo/access/HiddenAccessChecks.java

~~~java
package demo.access;

import java.io.IOException;
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenAccessChecks {
    private static int passed = 0;

    private static String secret() {
        return "PRIVATE_OK";
    }

    public static class Template {
        public static String message() {
            return "PUBLIC_OK";
        }
    }

    @FunctionalInterface
    interface CheckedAction {
        void run() throws Throwable;
    }

    private static byte[] readBytes(String resource) throws IOException {
        try (InputStream in = Objects.requireNonNull(
                HiddenAccessChecks.class.getResourceAsStream(resource), resource)) {
            return in.readAllBytes();
        }
    }

    private static void verify(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        passed++;
        System.out.println(label + "=PASS");
    }

    private static void expect(
            String label, Class<? extends Throwable> expected, CheckedAction action)
            throws Throwable {
        try {
            action.run();
        } catch (Throwable failure) {
            if (expected.isInstance(failure)) {
                passed++;
                System.out.println(label + "=" + expected.getSimpleName());
                return;
            }
            throw new AssertionError(label + ": wrong exception", failure);
        }
        throw new AssertionError(label + ": exception was expected");
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup owner = MethodHandles.lookup();
        byte[] localBytes = readBytes("HiddenAccessChecks$Template.class");
        byte[] foreignBytes = readBytes("/demo/foreign/ForeignTemplate.class");

        verify("ownerFull", owner.hasFullPrivilegeAccess());

        MethodHandles.Lookup hidden = owner.defineHiddenClass(localBytes, true);
        Class<?> hiddenClass = hidden.lookupClass();
        verify("validHidden", hiddenClass.isHidden());
        verify("validSamePackage",
                hiddenClass.getPackageName().equals(owner.lookupClass().getPackageName()));
        verify("validSameModule",
                hiddenClass.getModule() == owner.lookupClass().getModule());

        MethodHandle message = hidden.findStatic(
                hiddenClass, "message", MethodType.methodType(String.class));
        verify("validCall", "PUBLIC_OK".equals((String) message.invokeExact()));

        expect("wrongPackage", IllegalArgumentException.class,
                () -> owner.defineHiddenClass(foreignBytes, false));
        expect("publicLookup", IllegalAccessException.class,
                () -> MethodHandles.publicLookup().defineHiddenClass(localBytes, false));

        MethodHandles.Lookup reduced =
                owner.dropLookupMode(MethodHandles.Lookup.PRIVATE);
        verify("reducedFull", !reduced.hasFullPrivilegeAccess());
        expect("reducedLookup", IllegalAccessException.class,
                () -> reduced.defineHiddenClass(localBytes, false));

        expect("withoutNestmate", IllegalAccessException.class,
                () -> hidden.findStatic(
                        HiddenAccessChecks.class, "secret", MethodType.methodType(String.class)));

        MethodHandles.Lookup nestmate = owner.defineHiddenClass(
                localBytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        verify("nestHost",
                nestmate.lookupClass().getNestHost() == HiddenAccessChecks.class);
        MethodHandle secret = nestmate.findStatic(
                HiddenAccessChecks.class, "secret", MethodType.methodType(String.class));
        verify("withNestmate", "PRIVATE_OK".equals((String) secret.invokeExact()));

        expect("findHiddenByName", ClassNotFoundException.class,
                () -> Class.forName(hiddenClass.getName()));

        System.out.println("ALL_TESTS_PASS=" + passed);
    }
}
~~~

### Tệp 2 — src/demo/foreign/ForeignTemplate.java

~~~java
package demo.foreign;

public class ForeignTemplate {
    public static String message() {
        return "FOREIGN";
    }
}
~~~

Từ thư mục `project/`, tạo thư mục `out` rồi biên dịch **cả hai source file** cùng mức ngôn ngữ Java 17:

~~~bash
mkdir out
javac --release 17 -encoding UTF-8 -d out src/demo/access/HiddenAccessChecks.java src/demo/foreign/ForeignTemplate.java
java -cp out demo.access.HiddenAccessChecks
~~~

Chạy các lệnh trên trong terminal từ đúng thư mục dự án; trong Windows, PowerShell và `cmd` đều nhận dạng đường dẫn tương ứng khi sử dụng dấu `/` trong lệnh Java. Không cần Maven, Gradle hay dependency bên ngoài.

**Stdout mong đợi chính xác:**

~~~text
ownerFull=PASS
validHidden=PASS
validSamePackage=PASS
validSameModule=PASS
validCall=PASS
wrongPackage=IllegalArgumentException
publicLookup=IllegalAccessException
reducedFull=PASS
reducedLookup=IllegalAccessException
withoutNestmate=IllegalAccessException
nestHost=PASS
withNestmate=PASS
findHiddenByName=ClassNotFoundException
ALL_TESTS_PASS=13
~~~

Các phần chính của bài kiểm thử:

1. **`ownerFull`:** `MethodHandles.lookup()` được gọi ngay trong `HiddenAccessChecks`, có full privilege trong ngữ cảnh lớp đó.
2. **`validHidden`:** khi nhận bytes của `HiddenAccessChecks$Template.class`, `defineHiddenClass` tạo class mới và `isHidden()` trả `true`.
3. **`validSamePackage` / `validSameModule`:** xác minh hidden class thuộc ngữ cảnh package/module của lookup class. Lần chạy này sử dụng classpath và unnamed module.
4. **`validCall`:** `hidden.findStatic(...)` lấy phương thức `message()` từ lớp ẩn, `invokeExact()` trả `PUBLIC_OK`.
5. **`wrongPackage`:** bytes thật của `demo.foreign.ForeignTemplate` bị từ chối dù `owner` có quyền đầy đủ. Ngoại lệ đúng là `IllegalArgumentException`.
6. **`publicLookup`:** cùng local bytes nhưng lookup công khai thiếu full privilege, ném `IllegalAccessException`.
7. **`reducedFull` / `reducedLookup`:** loại mode `PRIVATE`; không còn full privilege, `defineHiddenClass` ném `IllegalAccessException`.
8. **`withoutNestmate`:** hidden class thành công nhưng không cùng nest với host, nên không tra cứu được `private static secret()`.
9. **`nestHost` / `withNestmate`:** với `ClassOption.NESTMATE`, hidden class cùng nest với host, tạo handle đến `secret()` thành công.
10. **`findHiddenByName`:** `Class.forName(hiddenClass.getName())` không tìm được hidden class vì tên của nó không phải tên nhị phân được bộ nạp lớp tìm kiếm theo cơ chế thông thường.

Tổng `13` là số lần `verify` hoặc `expect` ghi nhận đúng điều kiện. Nếu bất kỳ tình huống nào sai, chương trình ném `AssertionError` và không in dòng tổng kết thành công.

### Vì sao cần hai file .java?

`HiddenAccessChecks` và `ForeignTemplate` khai báo **hai package khác nhau**. Nếu chỉ dùng `String` tên resource như `"foreign/..."` mà bytecode vẫn nằm trong cùng package, bạn không thật sự kiểm tra điều kiện **sai package**.

Lớp `Template` được viết là `public static class` để nó có một phương thức `public static` đơn giản, không bị xung đột với mục tiêu của ca kiểm thử hợp lệ. `javac` tạo `HiddenAccessChecks$Template.class` bên cạnh class host; `readBytes(...)` nạp đúng bytes này theo classpath. File `ForeignTemplate.class` nằm dưới `out/demo/foreign/` và được đọc qua resource path tuyệt đối `/demo/foreign/ForeignTemplate.class`.

Phương thức `readBytes` dùng `try-with-resources` và `Objects.requireNonNull` để **lỗi thiếu resource không bị hiểu nhầm thành lỗi quyền của Lookup**. Trong bài thực tế, cần kiểm tra nguồn class bytes là tin cậy trước khi định nghĩa và khởi tạo.

## 9. Đọc kết quả đúng: lỗi quyền không giống lỗi class file

Các lỗi dưới đây thuộc **các giai đoạn khác nhau**:

| Lỗi/biểu hiện | Vấn đề thường nằm ở đâu? |
| --- | --- |
| `IllegalAccessException` khi `defineHiddenClass` | `Lookup` thiếu full privilege (như public lookup hoặc đã drop quyền). |
| `IllegalArgumentException` khi `defineHiddenClass` | Class file thuộc package khác lookup class; hoặc một điều kiện đầu vào `bytes` thuộc nhóm API báo `IllegalArgumentException`. |
| `ClassFormatError` | `bytes` không mang cấu trúc class file hợp lệ. |
| `UnsupportedClassVersionError` | Phiên bản class file trong bytes không được runtime hỗ trợ. |
| `VerifyError` / `LinkageError` | JVM không xác minh/liên kết được lớp theo một quy tắc tương ứng. |
| `IllegalAccessException` khi `findStatic` | Phương thức đích không truy cập được từ ngữ cảnh `Lookup`, kể cả trường hợp khác nest và thành viên `private`. |
| `NoSuchMethodException` khi `findStatic` | Tên hoặc `MethodType` yêu cầu không khớp thành viên cần tìm. |
| `WrongMethodTypeException` khi gọi handle | Kiểu lời gọi `invokeExact` không tương thích với `MethodHandle`. |
| `ClassNotFoundException` khi `Class.forName` | Đang cố tìm hidden class bằng tên thay vì giữ `Class<?>`/`Lookup`. |

**Đừng bắt `Exception` rồi coi mọi trường hợp là “thiếu quyền”.** Trong chương trình, `expect` nhận **một loại ngoại lệ cụ thể** cho từng ca, và một ngoại lệ ngoài dự kiến bị đánh dấu thất bại. Điều này giúp các lần nâng JDK hoặc thay bytecode không che khuất lỗi.

## 10. Những điểm dễ hiểu nhầm về access và nest

### Cùng runtime package có phải được truy cập private?

**Không.** Package-private và private là hai cấp truy cập khác nhau. Cùng runtime package có thể giúp truy cập thành viên *không khai báo modifier* trong các điều kiện hợp lệ, nhưng **không tự tạo quan hệ nest**. Ca `withoutNestmate` chứng minh điều này.

### Nếu Lookup trả về từ defineHiddenClass có full privilege, tại sao vẫn không truy cập được private của host?

`Lookup` mới mang ngữ cảnh của **hidden class**. Full privilege của nó áp dụng theo lookup class và **các nestmate của lookup class**. Khi chưa chọn `NESTMATE`, host không nằm trong nest của hidden class; do đó tra cứu `private` của host vẫn bị từ chối.

### Một class file thuộc package khác có thể được “sửa” bằng cách đổi thư mục?

**Không.** Class file ghi tên nội bộ của class. Chuyển file `.class` từ `demo/foreign` sang `demo/access` trên đĩa không biến nó thành class `demo.access.*` hợp lệ. Cần class bytes có tên/package tương ứng, được sinh/biên dịch và xác minh hợp lệ.

### Chỉ cần dùng privateLookupIn là có thể bỏ mọi hạn chế?

**Không.** `MethodHandles.privateLookupIn(Target.class, callerLookup)` yêu cầu `callerLookup` có quyền thích hợp, và với target ở module khác còn phụ thuộc quan hệ **reads/opens**. Nó không tự cấp quyền vượt cơ chế module. Một lookup có quyền private đối với target không mặc nhiên được phép định nghĩa hidden class nếu nó không còn **full privilege**, nhất là sau các chuyển ngữ cảnh qua module.

### Có nên dựa vào `Class.forName` để lấy lại hidden class?

**Không.** Một hidden class không có binary name bình thường để nạp bằng tên. Giữ `Lookup` được trả về, `lookupClass()`, các `MethodHandle` đã tra cứu hoặc đối tượng liên quan theo vòng đời thiết kế. Không khẳng định suffix của tên hidden class vì JVM sinh định danh không ổn định.

## 11. Checklist viết kiểm thử hồi quy trong dự án

- **Kiểm thử tích cực trước:** dùng bytes hợp lệ, đúng package và lookup có full privilege; xác nhận `isHidden()`, module/package và gọi được phương thức.
- **Tách từng lỗi:** giữ lookup đầy đủ quyền khi kiểm thử sai package, giữ bytes hợp lệ khi kiểm thử thiếu quyền.
- **Định danh ngoại lệ:** với `defineHiddenClass`, dự kiến `IllegalArgumentException` cho sai package, `IllegalAccessException` cho thiếu full privilege. Không dùng catch chung để che dấu sai khác.
- **Kiểm tra nest riêng:** thử không `NESTMATE` rồi thử có `NESTMATE` đối với cùng một thành viên `private` của host.
- **Đừng khởi tạo bytecode không tin cậy:** tham số `initialize=true` có thể kích hoạt class initializer; hidden class **không phải sandbox**.
- **Kiểm soát vòng đời:** `ClassOption.STRONG` có ý nghĩa về khả năng tồn tại/lifetime, không phải quyền truy cập. Test quyền và test unloading không nên trộn làm một.
- **Chạy trên JDK mục tiêu:** dùng `javac --release 17` hoặc mức ngôn ngữ được dự án hỗ trợ; chạy test trên runtime thực tế, vì không thể biên dịch class file phiên bản mới rồi kỳ vọng JVM cũ nạp được.
- **Không phát tán `Lookup` đặc quyền:** cung cấp `Lookup` hoặc MethodHandle có đặc quyền cho mã không tin cậy có thể mở rộng khả năng truy cập.
- **Dùng API chính thức:** `MethodHandles.Lookup.defineHiddenClass(...)` đã chính thức từ Java 15 và vẫn được hỗ trợ; không cần dùng các API định nghĩa lớp nội bộ đã lỗi thời.

## 12. Tài liệu tham khảo đang còn hiệu lực

1. [Java SE 24 — `MethodHandles.Lookup` API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): các điều kiện `defineHiddenClass`, full privilege, same package, kiểu ngoại lệ và truy cập phương thức.
2. [Java SE 24 — `MethodHandles` API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()` và `privateLookupIn(...)`.
3. [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): thiết kế và phạm vi sử dụng tính năng hidden class chính thức từ Java 15.
4. [Java Language Specification — Access Control](https://docs.oracle.com/javase/specs/jls/se24/html/jls-6.html#jls-6.6): phân biệt public, protected, package-private, private.
5. [Java Virtual Machine Specification — Access Control (`5.4.4)](https://docs.oracle.com/javase/specs/jvms/se24/html/jvms-5.html#jvms-5.4.4): ràng buộc truy cập JVM, bao gồm kiểm tra nestmate.

**Kết luận:** `Lookup` quyết định **bạn có quyền định nghĩa hidden class hay không**; package thực của bytes quyết định **bạn được định nghĩa nó trong ngữ cảnh đó hay không**; quan hệ nest quyết định **hidden class có thể truy cập `private` của host hay không**. Ba điều kiện cần được kiểm thử **riêng rẽ** để tránh chẩn đoán sai.